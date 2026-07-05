# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Gold set: 50 Exam P question/answer pairs with known-correct answers.

These are the *source cards* fed to the analog generator AND the reference
answers used by the checker. Content is real SOA Exam P material (counting,
conditional probability, Bayes, common distributions, expectation/variance,
covariance/correlation, joint distributions, CLT). Nothing here is AI-generated.

Each item: {"id", "topic", "front", "back"} where topic is one of
GeneralProbability / UnivariateRV / MultivariateRV.
"""

from __future__ import annotations

GP = "GeneralProbability"
UNI = "UnivariateRV"
MV = "MultivariateRV"

GOLD: list[dict] = [
    # --- General Probability (counting / independence / conditional / Bayes) --
    {"id": "g01", "topic": GP, "front": "A fair coin is flipped 3 times. How many equally likely ordered outcomes are there?", "back": "8 (2^3)"},
    {"id": "g02", "topic": GP, "front": "A fair 6-sided die is rolled 2 times. How many possible ordered outcomes are there?", "back": "36 (6^2)"},
    {"id": "g03", "topic": GP, "front": "How many possible outcomes when you toss a coin 4 times?", "back": "16 (2^4)"},
    {"id": "g04", "topic": GP, "front": "Events A and B are independent with P(A)=0.5 and P(B)=0.4. What is P(A and B)?", "back": "0.20"},
    {"id": "g05", "topic": GP, "front": "A and B are independent, P(A)=0.3, P(B)=0.5. Find the probability of the intersection P(A and B).", "back": "0.15"},
    {"id": "g06", "topic": GP, "front": "An event occurs independently with probability 0.2 on each of 3 trials. What is P(it occurs at least one time)?", "back": "0.488"},
    {"id": "g07", "topic": GP, "front": "A component fails with probability 0.1 each day, independently. P(at least one failure in 4 days)?", "back": "0.3439"},
    {"id": "g08", "topic": GP, "front": "A disease affects 1% of a population. A test is 99% sensitive and 99% specific. Given a positive test, P(has disease) by Bayes' theorem?", "back": "0.50"},
    {"id": "g09", "topic": GP, "front": "By Bayes' theorem, if P(D)=0.02, P(+|D)=0.9, P(+|not D)=0.05, find P(D|+).", "back": "≈0.269"},
    {"id": "g10", "topic": GP, "front": "P(A)=0.6, P(B)=0.5, P(A and B)=0.3. Find the conditional probability P(A|B).", "back": "0.6"},
    {"id": "g11", "topic": GP, "front": "From a standard 52-card deck, what is the probability of drawing an Ace?", "back": "1/13"},
    {"id": "g12", "topic": GP, "front": "P(A)=0.7, P(B)=0.4, P(A or B)=0.8. Find P(A and B).", "back": "0.3"},
    {"id": "g13", "topic": GP, "front": "Two dice are rolled. What is the probability the sum is 7?", "back": "1/6"},
    {"id": "g14", "topic": GP, "front": "A bag has 3 red and 2 blue balls. Draw 2 without replacement. P(both red)?", "back": "3/10"},
    {"id": "g15", "topic": GP, "front": "If P(A)=0.4 and A, B are mutually exclusive with P(B)=0.3, find P(A or B).", "back": "0.7"},
    {"id": "g16", "topic": GP, "front": "A fair coin is tossed 5 times. How many outcomes have exactly the given ordered sequence length (total possible outcomes)?", "back": "32 (2^5)"},

    # --- Univariate Random Variables -----------------------------------------
    {"id": "u01", "topic": UNI, "front": "X ~ Binomial(n=10, p=0.5). What is E[X], the expected value?", "back": "5"},
    {"id": "u02", "topic": UNI, "front": "X ~ Binomial(n=20, p=0.3). What is the mean E[X]?", "back": "6"},
    {"id": "u03", "topic": UNI, "front": "X ~ Binomial(n=8, p=0.25). Compute the expected value E[X].", "back": "2"},
    {"id": "u04", "topic": UNI, "front": "X ~ Poisson(lambda=3). What is Var(X), the variance?", "back": "3"},
    {"id": "u05", "topic": UNI, "front": "X ~ Poisson(lambda=5). What is the variance Var(X)?", "back": "5"},
    {"id": "u06", "topic": UNI, "front": "X ~ Poisson(lambda=2). Find Var(X).", "back": "2"},
    {"id": "u07", "topic": UNI, "front": "X ~ Exponential with rate lambda=2. What is E[X]?", "back": "0.5"},
    {"id": "u08", "topic": UNI, "front": "X ~ Exponential with rate lambda=4. What is the mean E[X]?", "back": "0.25"},
    {"id": "u09", "topic": UNI, "front": "X ~ Exponential with rate lambda=5. Find E[X].", "back": "0.2"},
    {"id": "u10", "topic": UNI, "front": "X ~ Uniform(0, 10). What is P(X < 3)?", "back": "0.30"},
    {"id": "u11", "topic": UNI, "front": "X ~ Uniform(0, 8). What is E[X]?", "back": "4"},
    {"id": "u12", "topic": UNI, "front": "X ~ Uniform(2, 6). What is the variance Var(X)?", "back": "4/3 ≈ 1.333"},
    {"id": "u13", "topic": UNI, "front": "X ~ Normal(mean=0, sd=1). What is P(X < 0)?", "back": "0.5"},
    {"id": "u14", "topic": UNI, "front": "X ~ Normal(mu=10, sigma=2). What is the 50th percentile (median)?", "back": "10"},
    {"id": "u15", "topic": UNI, "front": "X ~ Binomial(n=12, p=0.5). What is the expected number of successes E[X]?", "back": "6"},
    {"id": "u16", "topic": UNI, "front": "X ~ Geometric(p=0.25) counting trials to first success. What is E[X]?", "back": "4"},
    {"id": "u17", "topic": UNI, "front": "For a discrete RV with pmf P(X=1)=0.5, P(X=2)=0.5, what is E[X], the mean?", "back": "1.5"},
    {"id": "u18", "topic": UNI, "front": "X ~ Poisson(lambda=4). What is E[X]?", "back": "4"},

    # --- Multivariate Random Variables ---------------------------------------
    {"id": "m01", "topic": MV, "front": "For any random variable X, what does Cov(X, X) equal?", "back": "Var(X)"},
    {"id": "m02", "topic": MV, "front": "If X and Y are independent, what is Cov(X, Y)?", "back": "0"},
    {"id": "m03", "topic": MV, "front": "X and Y are independent with Var(X)=2 and Var(Y)=3. What is Var(X+Y)?", "back": "5"},
    {"id": "m04", "topic": MV, "front": "Cov(X,Y)=6, sd(X)=2, sd(Y)=6. Find the correlation coefficient.", "back": "0.5"},
    {"id": "m05", "topic": MV, "front": "By the Central Limit Theorem, the distribution of the sample mean of many iid variables is approximately which distribution?", "back": "Normal"},
    {"id": "m06", "topic": MV, "front": "The joint pdf f(x,y)=1 on the unit square 0<x<1, 0<y<1. What is the marginal density of X?", "back": "1 on (0,1)"},
    {"id": "m07", "topic": MV, "front": "Var(X)=4, Var(Y)=9, Cov(X,Y)=2. Find Var(X+Y).", "back": "17"},
    {"id": "m08", "topic": MV, "front": "For the sample mean of n iid variables each with sd sigma, the sd of the mean scales as?", "back": "sigma/sqrt(n)"},
    {"id": "m09", "topic": MV, "front": "If E[X]=2, E[Y]=3 and X,Y independent, what is E[XY]?", "back": "6"},
    {"id": "m10", "topic": MV, "front": "Correlation of X with itself, corr(X,X), equals?", "back": "1"},
    {"id": "m11", "topic": MV, "front": "X and Y are independent, Var(X)=5, Var(Y)=7. Find Var(X - Y).", "back": "12"},
    {"id": "m12", "topic": MV, "front": "Joint pdf f(x,y)=2 on 0<x<y<1. What is P(Y>0.5)?", "back": "0.75"},
    {"id": "m13", "topic": MV, "front": "If corr(X,Y)=0 and both are normal and jointly normal, X and Y are?", "back": "independent"},
    {"id": "m14", "topic": MV, "front": "E[X]=1, Var(X)=4. For Y=2X+3, find Var(Y).", "back": "16"},
    {"id": "m15", "topic": MV, "front": "For a bivariate normal with means 0, unit variances, corr 0.5, what is E[Y|X=x]?", "back": "0.5x"},
    {"id": "m16", "topic": MV, "front": "Cov(2X, 3Y) in terms of Cov(X,Y)?", "back": "6 Cov(X,Y)"},
]

assert len(GOLD) == 50, f"gold set must have 50 items, has {len(GOLD)}"


def held_out(n: int = 20) -> list[dict]:
    """A deterministic held-out slice (every-other item, first n)."""
    return GOLD[::2][:n]


def training(n: int = 20) -> list[dict]:
    return GOLD[1::2]
