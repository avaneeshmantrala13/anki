// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! BrainLift: deterministic per-topic mastery & coverage aggregation.
//!
//! Given a list of topics (each identified by an Anki search string), compute
//! per-topic statistics that power the BrainLift dashboard, study planner and
//! readiness model: how many cards the topic has, how many have been studied,
//! how many are "mastered" (current FSRS retrievability above a threshold),
//! the total number of reviews, and the mean retrievability.
//!
//! This contains no AI: every number is derived directly from the collection's
//! existing review history and FSRS memory state.

use anki_proto::stats::TopicMastery;
use anki_proto::stats::TopicMasteryRequest;
use anki_proto::stats::TopicMasteryResponse;
use fsrs::FSRS;
use fsrs::FSRS5_DEFAULT_DECAY;

use crate::prelude::*;
use crate::search::SortMode;

/// Default retrievability at/above which a card is considered "mastered" when
/// the caller does not specify a threshold.
const DEFAULT_MASTERED_THRESHOLD: f32 = 0.9;

impl Collection {
    /// Compute mastery & coverage for each requested topic.
    pub(crate) fn compute_topic_mastery(
        &mut self,
        input: TopicMasteryRequest,
    ) -> Result<TopicMasteryResponse> {
        let threshold = if input.mastered_threshold <= 0.0 {
            DEFAULT_MASTERED_THRESHOLD
        } else {
            input.mastered_threshold
        };
        let timing = self.timing_today()?;
        let fsrs = FSRS::new(None)?;

        let mut topics = Vec::with_capacity(input.topics.len());
        for topic in &input.topics {
            // Collect the matching cards, then drop the search guard (and its
            // temporary table) before aggregating.
            let cards = {
                let guard = self.search_cards_into_table(&topic.search, SortMode::NoOrder)?;
                guard.col.storage.all_searched_cards()?
            };

            let total_cards = cards.len() as u32;
            let mut reviewed_cards = 0u32;
            let mut mastered_cards = 0u32;
            let mut total_reviews = 0u32;
            // Retrievability requires an FSRS memory state, which only exists
            // when FSRS is enabled, so it is tracked (and averaged) separately
            // from the plain "has been studied" count.
            let mut cards_with_retrievability = 0u32;
            let mut retrievability_sum = 0.0f32;

            for card in &cards {
                total_reviews += card.reps;
                if card.reps > 0 {
                    reviewed_cards += 1;
                }
                if let Some(state) = card.memory_state {
                    let elapsed_seconds =
                        card.seconds_since_last_review(&timing).unwrap_or_default();
                    let retrievability = fsrs.current_retrievability_seconds(
                        state.into(),
                        elapsed_seconds,
                        card.decay.unwrap_or(FSRS5_DEFAULT_DECAY),
                    );
                    cards_with_retrievability += 1;
                    retrievability_sum += retrievability;
                    if retrievability >= threshold {
                        mastered_cards += 1;
                    }
                }
            }

            let average_retrievability = if cards_with_retrievability > 0 {
                retrievability_sum / cards_with_retrievability as f32
            } else {
                0.0
            };

            topics.push(TopicMastery {
                name: topic.name.clone(),
                total_cards,
                reviewed_cards,
                mastered_cards,
                total_reviews,
                average_retrievability,
                covered: total_cards > 0,
            });
        }

        Ok(TopicMasteryResponse { topics })
    }
}

#[cfg(test)]
mod test {
    use anki_proto::stats::TopicMasteryRequest;
    use anki_proto::stats::TopicSearch;

    use crate::config::BoolKey;
    use crate::prelude::*;

    fn request(topics: &[(&str, &str)], threshold: f32) -> TopicMasteryRequest {
        TopicMasteryRequest {
            topics: topics
                .iter()
                .map(|(name, search)| TopicSearch {
                    name: name.to_string(),
                    search: search.to_string(),
                })
                .collect(),
            mastered_threshold: threshold,
        }
    }

    fn add_tagged_note(col: &mut Collection, tag: &str) {
        let mut note = col.basic_notetype().new_note();
        note.tags = vec![tag.to_string()];
        col.add_note(&mut note, DeckId(1)).unwrap();
    }

    /// A topic whose search matches nothing reports zero cards and is not
    /// covered.
    #[test]
    fn empty_topic_is_uncovered() -> Result<()> {
        let mut col = Collection::new();
        let resp = col.compute_topic_mastery(request(&[("Probability", "tag:ExamP::Nope")], 0.0))?;
        assert_eq!(resp.topics.len(), 1);
        let topic = &resp.topics[0];
        assert_eq!(topic.name, "Probability");
        assert_eq!(topic.total_cards, 0);
        assert_eq!(topic.reviewed_cards, 0);
        assert!(!topic.covered);
        Ok(())
    }

    /// Cards that exist but have never been reviewed are counted and covered,
    /// but contribute no reviews and no mastery.
    #[test]
    fn unreviewed_cards_are_covered_but_not_mastered() -> Result<()> {
        let mut col = Collection::new();
        add_tagged_note(&mut col, "ExamP::Probability");
        add_tagged_note(&mut col, "ExamP::Probability");
        add_tagged_note(&mut col, "ExamP::Calculus");

        let resp = col.compute_topic_mastery(
            request(
                &[
                    ("Probability", "tag:ExamP::Probability"),
                    ("Calculus", "tag:ExamP::Calculus"),
                ],
                0.0,
            ),
        )?;

        let probability = &resp.topics[0];
        assert_eq!(probability.total_cards, 2);
        assert!(probability.covered);
        assert_eq!(probability.reviewed_cards, 0);
        assert_eq!(probability.mastered_cards, 0);
        assert_eq!(probability.total_reviews, 0);
        assert_eq!(probability.average_retrievability, 0.0);

        let calculus = &resp.topics[1];
        assert_eq!(calculus.total_cards, 1);
        assert!(calculus.covered);
        Ok(())
    }

    /// After a card is reviewed it gains an FSRS memory state, so it counts as
    /// reviewed and (just-reviewed → retrievability ~1.0) as mastered under the
    /// default threshold.
    #[test]
    fn reviewed_card_counts_as_reviewed_and_mastered() -> Result<()> {
        let mut col = Collection::new();
        // Enable FSRS so reviewing populates a memory state (and thus
        // retrievability / mastery).
        col.set_config_bool(BoolKey::Fsrs, true, false)?;
        add_tagged_note(&mut col, "ExamP::Probability");

        // Study the single due card with a passing grade.
        col.answer_easy();
        col.clear_study_queues();

        let resp =
            col.compute_topic_mastery(request(&[("Probability", "tag:ExamP::Probability")], 0.0))?;
        let topic = &resp.topics[0];
        assert_eq!(topic.total_cards, 1);
        assert_eq!(topic.reviewed_cards, 1);
        assert!(topic.total_reviews >= 1);
        assert_eq!(topic.mastered_cards, 1);
        assert!(topic.average_retrievability > 0.5);
        Ok(())
    }
}
