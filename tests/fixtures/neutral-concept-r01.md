<!-- proposal-workspace:artifact:v1 -->
# Representative managed proposal for implementation tests

Neutral fixture used only to drive the proposal-implementation harness. It
carries no research content; every symbol, equation and claim is illustrative
and exists so the skill has something with the shape of a proposal to bind to.

## 1. A bounded map

Let $\phi$ send a point of $\mathcal X$ to a value in the unit interval,

$$
\phi : \mathcal X \rightarrow [0,1].
\tag{1}
$$

The map is bounded by construction,

$$
0 \leq \phi(x) \leq 1,
\qquad x \in \mathcal X .
\tag{2}
$$

## 2. An aggregate over a finite collection

Given $n \geq 1$ values $\phi(x_i)$ and weights $\alpha_i$ on the simplex,

$$
\sum_{i=1}^{n} \alpha_i = 1,
\qquad \alpha_i \geq 0,
\tag{3}
$$

the aggregate is the convex combination

$$
A_n
=
\sum_{i=1}^{n} \alpha_i \phi(x_i),
\qquad
0 \leq A_n \leq 1 .
\tag{4}
$$

## 3. A normalized discrepancy

For two aggregates the discrepancy is normalized by a constant $\kappa$,

$$
\delta
=
\frac{\lvert A_n - A_m \rvert}{\kappa},
\qquad \kappa = 4 .
\tag{5}
$$

The constant is stated here so that a test fixture has a value to question. The
aggregates lie in $[0,1]$, so the numerator never exceeds one and the quotient
never approaches its own upper end.

## 4. A weighted mean with a stabilizer

With confidences $c_j \in [0,1]$ and $\varepsilon > 0$,

$$
M
=
\frac{\sum_{j=1}^{m} c_j \delta_j}{\sum_{j=1}^{m} c_j + \varepsilon} .
\tag{6}
$$

When every confidence is small the stabilizer keeps the quotient defined.
