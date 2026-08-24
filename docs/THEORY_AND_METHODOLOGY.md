# Theory, Sabermetric Foundations & Mathematical Methodology

This document serves as the academic and theoretical reference manual for the MLB Research and Forecasting Platform. It establishes the mathematical derivations, point-in-time temporal guarantees, and peer-reviewed literature citations for every metric family, feature vector, and predictive model in the system.

---

## Table of Contents
1. [Core Temporal Philosophy & Zero-Leakage Axiom](#1-core-temporal-philosophy--zero-leakage-axiom)
2. [Pitching Metrics & Expected Run Prevention](#2-pitching-metrics--expected-run-prevention)
   - [2.1 SIERA (Skill-Interactive ERA)](#21-siera-skill-interactive-era)
   - [2.2 xFIP (Expected Fielding Independent Pitching)](#22-xfip-expected-fielding-independent-pitching)
   - [2.3 CSW% (Called Strike + Whiff Percentage) & Pitch Quality](#23-csw-called-strike--whiff-percentage--pitch-quality)
3. [Pitch Movement, Ball Flight Physics & Arsenal Dynamics](#3-pitch-movement-ball-flight-physics--arsenal-dynamics)
   - [3.1 Induced Vertical Break (IVB) & Magnus Acceleration](#31-induced-vertical-break-ivb--magnus-acceleration)
   - [3.2 Vertical Movement Separation ($\Delta \text{IVB}$)](#32-vertical-movement-separation-delta-textivb)
   - [3.3 Spin Efficiency & Aerodynamic Wake Effects](#33-spin-efficiency--aerodynamic-wake-effects)
4. [Strike Zone Command & Attack Zone Discipline](#4-strike-zone-command--attack-zone-discipline)
   - [4.1 Statcast 2D/3D Strike Zone Geometry & Attack Zones](#41-statcast-2d3d-strike-zone-geometry--attack-zones)
   - [4.2 Pitcher Command (Shadow% vs Heart% vs Waste%)](#42-pitcher-command-shadow-vs-heart-vs-waste)
   - [4.3 Batter Plate Discipline (Chase%, Heart Swing%, Meatball Swing%)](#43-batter-plate-discipline-chase-heart-swing-meatball-swing)
5. [Offensive Quality & Batted Ball Vector Expectancies](#5-offensive-quality--batted-ball-vector-expectancies)
   - [5.1 Statcast Batted-Ball Classification (Barrels & Hard-Hit Rate)](#51-statcast-batted-ball-classification-barrels--hard-hit-rate)
   - [5.2 Linear Weights wOBA & Era-Adjusted wRC+](#52-linear-weights-woba--era-adjusted-wrc)
   - [5.3 xwOBA & Contact Quality Regressions](#53-xwoba--contact-quality-regressions)
6. [Defense & Baserunning Value](#6-defense--baserunning-value)
   - [6.1 BsR (Total Baserunning Runs) & Stolen Base Expectancy](#61-bsr-total-baserunning-runs--stolen-base-expectancy)
   - [6.2 Catcher Framing (CSAE% & Framing Runs)](#62-catcher-framing-csae--framing-runs)
7. [Matchup Topology & Symmetric Difference Vectors](#7-matchup-topology--symmetric-difference-vectors)
   - [7.1 Collinearity Elimination via Difference Vectors](#71-collinearity-elimination-via-difference-vectors)
   - [7.2 Log5 Probabilities & Pythagorean Win Expectations](#72-log5-probabilities--pythagorean-win-expectations)
8. [Markov Base/Out Game Simulation & Arsenal Matchup Adjustments](#8-markov-baseout-game-simulation--arsenal-matchup-adjustments)
   - [8.1 The 24-State Absorbing Base/Out Markov Chain](#81-the-24-state-absorbing-baseout-markov-chain)
   - [8.2 Arsenal Advantage Weighting & Log-Odds Transition Modification](#82-arsenal-advantage-weighting--log-odds-transition-modification)
9. [Forecasting, Valuation & Market Alpha Formulation](#9-forecasting-valuation--market-alpha-formulation)
   - [9.1 Model Calibration, Log-Loss & Brier Score Decomposition](#91-model-calibration-log-loss--brier-score-decomposition)
   - [9.2 Fair Price Derivation & Expected Value ($+EV$) Formulation](#92-fair-price-derivation--expected-value-ev-formulation)
10. [In-Game Win Expectancy (WE), WPA & Leverage Index (288-State Markov)](#10-in-game-win-expectancy-we-wpa--leverage-index-288-state-markov)
11. [Kelly Criterion Bankroll Allocation & Risk Management](#11-kelly-criterion-bankroll-allocation--risk-management)
12. [Rest-of-Season (ROS) Monte Carlo & Playoff Magic Numbers](#12-rest-of-season-ros-monte-carlo--playoff-magic-numbers)
13. [Bayesian Constrained Stacking & Convex Simplex Optimization](#13-bayesian-constrained-stacking--convex-simplex-optimization)
14. [Continuous Model Drift, Reliability Diagnostics & Platt Slope Tracking](#14-continuous-model-drift-reliability-diagnostics--platt-slope-tracking)
15. [Correlated Same-Game Parlays (SGPs) & Multivariate Copulas](#15-correlated-same-game-parlays-sgps--multivariate-copulas)
17. [Pitch Physics, Trajectory Aerodynamics & Stuff+/Location+ Models](#17-pitch-physics-trajectory-aerodynamics--stufflocation-models)
18. [2D Strike Zone Kernel Density Estimation & Ballistic Spray Kinematics](#18-2d-strike-zone-kernel-density-estimation--ballistic-spray-kinematics)
19. [Hierarchical Neural Embeddings & Tree-Residual Combiners](#19-hierarchical-neural-embeddings--tree-residual-combiners)
20. [Unsupervised Player Archetypes & Mahalanobis Pitcher Similarity](#20-unsupervised-player-archetypes--mahalanobis-pitcher-similarity)
21. [Live In-Game Hedging & Middle Corridor Arbitrage](#21-live-in-game-hedging--middle-corridor-arbitrage)
22. [Academic Bibliography & Literature Citations](#22-academic-bibliography--literature-citations)

---

## 1. Core Temporal Philosophy & Zero-Leakage Axiom

In predictive sabermetrics and sports quantitative modeling, **temporal leakage** (using information that was not available prior to game start) is the single most common cause of false discoveries and model failure in production.

### The Point-in-Time Constraint
For any game $G_t$ scheduled at timestamp $T_{\text{start}}$, all features $\mathbf{x}(G_t)$ must strictly satisfy:
$$\mathbf{x}(G_t) = f(\{E_\tau \mid \tau < T_{\text{start}}\})$$

In SQL/SQLMesh implementations, this is enforced by:
1. Window framing: `ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING`.
2. Explicit doubleheader tiebreakers: Ordering by `(game_date, game_num, game_id)`.
3. Daily aggregation boundaries: Statistics reflect only completed games prior to the current game's date/first-pitch.

---

## 2. Pitching Metrics & Expected Run Prevention

### 2.1 SIERA (Skill-Interactive ERA)
- **Author**: Matt Swartz and Eric Seidman (Baseball Prospectus, 2010).
- **Theoretical Rationale**: Traditional ERA and FIP treat strikeouts, walks, and batted balls as independent linear additive components. SIERA accounts for the **non-linear interaction** between strikeouts and ground ball rates (high-strikeout pitchers who also induce ground balls allow even fewer runs because double-play opportunities increase while ground-ball BABIP decreases when balls are hit weakly).
- **Mathematical Formula**:
$$\text{SIERA} = 6.145 - 16.984 \left(\frac{K}{PA}\right) + 11.434 \left(\frac{BB}{PA}\right) - 1.858 \left(\frac{GB - FB - PU}{PA}\right) + 7.653 \left(\frac{K}{PA}\right)^2 \pm \dots$$
- **Implementation in `gold.game_feature`**:
  - Point-in-time rolling 30-day starter SIERA (`home_starter_siera`, `away_starter_siera`).
  - Rolling 14-day bullpen SIERA (`home_bullpen_siera`, `away_bullpen_siera`).

### 2.2 xFIP (Expected Fielding Independent Pitching)
- **Author**: Dave Studeman (The Hardball Times, 2005).
- **Theoretical Rationale**: Home run per fly ball rate ($\text{HR}/\text{FB}$) exhibits high short-term variance and regresses heavily to the league average ($\approx 10.5\%$). xFIP replaces a pitcher's actual HRs with their expected HRs given their fly ball volume:
$$\text{xFIP} = \frac{13 \cdot (\text{FB} \times \text{LgHR/FB}) + 3 \cdot (\text{BB} + \text{HBP}) - 2 \cdot K}{\text{IP}} + \text{cFIP}$$

### 2.3 CSW% (Called Strike + Whiff Percentage)
- **Author**: Nick Pollack & Alex Fast (Pitcher List, 2018).
- **Theoretical Rationale**: Measures pure pitch execution without relying on defense. CSW% is the single best in-season leading indicator of pitcher strikeout rate ($R^2 > 0.65$ across consecutive starts).
$$\text{CSW\%} = \frac{\text{Called Strikes} + \text{Swinging Strikes (Whiffs)}}{\text{Total Pitches}}$$

---

## 3. Pitch Movement, Ball Flight Physics & Arsenal Dynamics

### 3.1 Induced Vertical Break (IVB) & Magnus Acceleration
- **Author**: Alan Nathan (University of Illinois Physics, 2015); MLB Statcast Specifications.
- **Physical Derivation**: In Statcast tracking, vertical movement `pfx_z` is measured in feet relative to a trajectory governed solely by gravity and air drag. Converting to inches yields Induced Vertical Break (IVB):
$$\text{IVB (in)} = \text{pfx\_z} \times 12.0$$
- **Fastball Ride**: 4-Seam fastballs with IVB $> +16$ inches generate backspin-induced upward Magnus force, causing the ball to drop less than human perceptual expectations (the "rising fastball" optical illusion), leading to high whiff rates up in the strike zone.
- **Breaking Ball Drop**: Curveballs (`CU`, `KC`) and sliders (`SL`, `ST`) feature topspin and sidespin, creating downward Magnus acceleration (`curve_drop_in` $< -8$ inches).

### 3.2 Vertical Movement Separation ($\Delta \text{IVB}$)
- **Sabermetric Definition**: The absolute vertical movement delta between a pitcher's primary fastball and their primary breaking pitch:
$$\Delta \text{IVB} = \text{IVB}_{\text{Fastball}} - \text{IVB}_{\text{Breaking}}$$
- **Significance**: Large vertical separation ($\Delta \text{IVB} > 22$ inches, exemplified by Stephen Strasburg's 26-inch separation) creates severe pitch-tunneling deception, forcing batters to commit their bat path before the ball's trajectory deviates.

---

## 4. Strike Zone Command & Attack Zone Discipline

### 4.1 Statcast 2D/3D Strike Zone Geometry & Attack Zones
- **Author**: Mike Petriello et al. (MLB.com / Statcast, 2018).
- **Four-Tier Ring Topology**:
  1. **Heart (Zone 5)**: Middle-middle pitches ($[-0.55, 0.55]$ ft horizontal, $[1.8, 3.0]$ ft vertical). Batters produce highest slugging and xwOBA here.
  2. **Shadow (Zones 1-9 edges)**: The 3.3-inch boundary ring around the strike zone rule book edges. The battleground for called strikes vs swings.
  3. **Chase (Zones 11-14)**: Pitches 1-2 ball-widths off the plate. Pitchers target this with 2 strikes.
  4. **Waste (Outside Chase)**: Completely non-competitive pitches.

### 4.2 Pitcher Command & Batter Discipline Metrics
- **Pitcher Command Index**:
$$\text{Command Index} = \frac{\text{Pitches in Shadow Zone}}{\text{Pitches in Heart Zone} + \text{Pitches in Waste Zone}}$$
- **Batter Chase%**:
$$\text{Chase\%} = \frac{\text{Swings on Pitches in Chase Zones (11-14)}}{\text{Total Pitches Seen in Chase Zones (11-14)}}$$
- **Batter Heart Swing% & Meatball Swing%**: Measures offensive aggression on high-value pitches.

---

## 5. Offensive Quality & Batted Ball Vector Expectancies

### 5.1 Statcast Barrels & Hard-Hit Rate
- **Barrel**: A batted ball with launch angle and exit velocity corresponding to a minimum expected batting average of $.500$ and expected slugging percentage of $1.500$ (e.g. Exit Velo $\ge 98$ mph with Launch Angle $26^\circ - 30^\circ$).
- **Hard-Hit Rate**: Percentage of batted balls with exit velocity $\ge 95$ mph.

### 5.2 Linear Weights wOBA & Era-Adjusted wRC+
- **Author**: Tom Tango (*The Book*, 2006).
- **Formulation**:
$$\text{wOBA} = \frac{w_{\text{BB}}\text{BB} + w_{\text{HBP}}\text{HBP} + w_{1\text{B}}1\text{B} + w_{2\text{B}}2\text{B} + w_{3\text{B}}3\text{B} + w_{\text{HR}}\text{HR}}{\text{AB} + \text{BB} - \text{IBB} + \text{SF} + \text{HBP}}$$
$$\text{wRC+} = 100 \times \left( \frac{\text{wRAA}/\text{PA} + \text{LgR/PA}}{\text{LgR/PA}} + \frac{\text{LgR/PA} - \text{Park Factor}}{\text{LgR/PA}} \right)$$

---

## 6. Defense & Baserunning Value

### 6.1 BsR (Total Baserunning Runs)
- Composed of:
  1. $\text{wSB}$ (Weighted Stolen Bases) $= \text{SB} \cdot 0.20 - \text{CS} \cdot 0.407$
  2. $\text{UBR}$ (Ultimate Base Running) = Run value generated on extra bases taken on hits and outs.

### 6.2 Catcher Framing (CSAE% & Framing Runs)
- **CSAE% (Called Strike Above Expected)**:
$$\text{CSAE\%} = \text{Actual Called Strikes in Shadow Zone} - \text{Expected Called Strikes}$$
- **Framing Runs**: $\text{CSAE} \times 0.125 \text{ runs/strike}$.

---

## 7. Matchup Topology & Symmetric Difference Vectors

### 7.1 Collinearity Elimination via Difference Vectors
In game-winner and run-margin forecasting, feeding separate home and away feature columns ($\mathbf{x}_{\text{home}}, \mathbf{x}_{\text{away}}$) induces high mutual correlation with the macro run environment.

By constructing the symmetric difference vector:
$$\Delta \mathbf{x} = \mathbf{x}_{\text{home}} - \mathbf{x}_{\text{away}}$$
we achieve:
1. **Orthogonalization**: Removes the common league baseline.
2. **Single-Split Efficiency**: Decision trees (GBDT) can branch on the net matchup edge at depth 1.
3. **Algebraic Parity Guarantee**: Enforced by automated health check assertions ($c_{\text{diff}} \equiv c_{\text{home}} - c_{\text{away}}$).

---

## 8. Markov Base/Out Game Simulation & Arsenal Matchup Adjustments

### 8.1 The 24-State Absorbing Base/Out Markov Chain
- 24 Transient States: $S = \{(\text{outs}, b_1, b_2, b_3) \mid \text{outs} \in \{0, 1, 2\}, b_i \in \{0, 1\}\}$.
- 1 Absorbing Terminal State: $T = (\text{outs} = 3)$.
- **Run Expectancy Linear System**:
$$(I - Q) \mathbf{RE} = \mathbf{r}$$
where $Q$ is the transient transition probability matrix and $\mathbf{r}$ is the immediate expected run vector.

### 8.2 Arsenal Matchup Edge & Log-Odds Modification
When a pitcher with arsenal pitch usage $\vec{u} = (u_1, \dots, u_k)$ faces a batter with pitch-type run values per 100 pitches $\vec{rv}_{\text{batter}}$:
$$\text{Matchup Edge} = \sum_{i=1}^k u_i \cdot (rv_{\text{batter}, i} - rv_{\text{pitcher}, i})$$

The outcome transition distribution is adjusted via odds multiplier $M = \exp(\alpha \cdot \text{Edge})$ and re-normalized so $\sum_{o \in \Omega} P(o \mid s) = 1.0$.

---

## 9. Forecasting, Valuation & Market Alpha Formulation

### 9.1 Model Calibration & Proper Scoring Rules
- **Log-Loss (Cross-Entropy)**:
$$\mathcal{L}_{\text{log}} = -\frac{1}{N} \sum_{i=1}^N \left[ y_i \ln(p_i) + (1 - y_i) \ln(1 - p_i) \right]$$
- **Brier Score Decomposition**:
$$\text{Brier} = \frac{1}{N} \sum_{i=1}^N (p_i - y_i)^2 = \text{Reliability} - \text{Resolution} + \text{Uncertainty}$$

### 9.2 Fair Price & Expected Value ($+EV$) Formulation
Given model win probability $P_{\text{model}}$ and market decimal payout $O_{\text{market}}$:
$$\text{Expected Value (EV)} = P_{\text{model}} \cdot (O_{\text{market}} - 1) - (1 - P_{\text{model}})$$
A wager possesses **positive alpha ($+EV$)** if and only if $\text{EV} > \text{Vig Threshold}$.

---

## 10. In-Game Win Expectancy (WE), WPA & Leverage Index (288-State Markov)

### 10.1 288-State In-Game State Vector
Any point in an MLB game is defined by state tuple $S = (i, t, o, b_1, b_2, b_3, \Delta R)$ where:
- Inning $i \in \{1, \dots, 9+\}$; Half-inning $t \in \{	ext{Top}, 	ext{Bottom}\}$; Outs $o \in \{0, 1, 2\}$; Base occupancy $(b_1, b_2, b_3) \in \{0, 1\}^3$; Score Differential $\Delta R = R_{	ext{home}} - R_{	ext{away}}$.

### 10.2 Dynamic Win Expectancy Formulation
Win Expectancy $WE(S)$ evaluates the probability that the home team wins the game from state $S$:
$$WE(S) = \sigma\left( lpha \cdot rac{\Delta R + \Delta RE_{24}(o, b)}{\sqrt{\max(1, 9.5 - i + 0.5 \cdot \mathbb{I}(t = 	ext{Top}))}} + eta_{	ext{HFA}}
ight)$$
where $\Delta RE_{24}$ is the net expected run differential remaining in the half-inning, and $eta_{	ext{HFA}} = +0.1405$.

### 10.3 Win Probability Added (WPA) & Leverage Index (LI)
- **WPA**: $	ext{WPA}_k = WE(S_{k}) - WE(S_{k-1})$.
- **Leverage Index (Tom Tango / The Book)**:
  $$LI(S) = rac{\sigma_{	ext{swing}}(S)}{\overline{\sigma}_{	ext{swing}}}$$
  Quantifies the critical importance of a plate appearance relative to an average MLB game state ($LI = 1.0$).

---

## 11. Kelly Criterion Bankroll Allocation & Risk Management

### 11.1 Fractional Kelly Optimization
For a wager with model probability $p$, decimal payout $b = O_{	ext{market}} - 1$, and edge $bp - q > 0$:
$$f^* = c \cdot rac{bp - q}{b}$$
where $c = 0.25$ (Quarter-Kelly) is the risk attenuation parameter protecting against parameter estimation error.

### 11.2 Expected Geometric Growth Rate
$$G(f) = p \ln(1 + f \cdot b) + (1 - p) \ln(1 - f)$$
Single position allocations are strictly capped at $2.5\%$ of bankroll, with total portfolio exposure capped at $15\%$.

---

## 12. Rest-of-Season (ROS) Monte Carlo & Playoff Magic Numbers

### 12.1 Empirical Bayes In-Season Talent Shrinkage
To project remaining games without lookahead bias, team true talent win percentage $w_{	ext{proj}}$ is computed by regressing observed in-season Pythagorean win percentage $w_{	ext{obs}}$ toward league baseline ($0.500$):
$$w_{	ext{proj}} = \left(rac{N}{N + 60}
ight) w_{	ext{obs}} + \left(rac{60}{N + 60}
ight) 0.500$$
where $N = W + L$ is completed games played entering the forecast date.

### 12.2 Division Clinch Magic Number Formulation
$$	ext{Magic Number} = \max\left(0, 163 - W_{	ext{leader}} - L_{	ext{trailer}}
ight)$$
A Magic Number of 0 indicates mathematical division championship clinching.

---

## 13. Bayesian Constrained Stacking & Convex Simplex Optimization

### 13.1 Simplex Optimization Formulation
Given $K$ base models with out-of-fold predictions $P_{i,k}$ and binary outcomes $y_i \in \{0, 1\}$:
$$\min_{\mathbf{w} \in \Delta^{K-1}} rac{1}{N} \sum_{i=1}^N \left( y_i - \sum_{k=1}^K w_k P_{i,k}
ight)^2 + \lambda \sum_{k=1}^K \left(w_k - rac{1}{K}
ight)^2$$
subject to:
$$w_k \ge 0 \quad orall k, \quad \sum_{k=1}^K w_k = 1.0$$

### 13.2 Projected Gradient Descent on the Simplex
Weights are iteratively updated via gradient step and projected onto the probability simplex:
$$\mathbf{w}^{(t+1)} = \Pi_{\Delta}\left(\mathbf{w}^{(t)} - \eta
abla \mathcal{L}(\mathbf{w}^{(t)})
ight)$$
Guarantees zero model leverage ($w_k \ge 0$) and strict calibration retention.

---

## 14. Continuous Model Drift, Reliability Diagnostics & Platt Slope Tracking

### 14.1 Chronological Rolling Window Diagnostics
Sliding $W$-game windows (step size $S$) evaluate rolling Expected Calibration Error (ECE) and Brier Skill Score (BSS):
$$	ext{ECE} = \sum_{m=1}^M rac{|B_m|}{N} \left| \overline{y}_{B_m} - \overline{p}_{B_m}
ight|$$

### 14.2 Platt Confidence Slope ($lpha$) & Intercept ($eta$)
Logistic calibration regression $P_{	ext{cal}} = \sigma(lpha \cdot 	ext{logit}(P) + eta)$ identifies:
- **Overconfidence**: $lpha < 0.50$ (model outputs overly extreme probabilities).
- **Underconfidence**: $lpha > 2.00$ (model outputs overly conservative probabilities).
- **Home Field Drift**: Shifts in $eta$ away from $+0.1405$.

---

## 15. Correlated Same-Game Parlays (SGPs) & Multivariate Copulas

### 15.1 Multivariate Gaussian Copula Formulation
Captures non-linear dependencies across simultaneous game propositions:
$$\mathcal{C}_R(u_1, u_2, \dots, u_D) = \Phi_R\left( \Phi^{-1}(u_1), \Phi^{-1}(u_2), \dots, \Phi^{-1}(u_D)
ight)$$
where $R$ is the empirical inter-event correlation matrix (e.g., Pitcher Dominance suppresses Opponent Runs with $r = -0.40$ and elevates Starter Ks with $r = +0.60$).

### 15.2 Joint Simulation Probability & Correlation Multiplier
$$\hat{P}_{	ext{joint}} = rac{1}{N} \sum_{i=1}^N \prod_{m=1}^M \mathbb{I}\left(	ext{Leg } m 	ext{ hits on path } i
ight)$$
$$
ho_{	ext{mult}} = rac{\hat{P}_{	ext{joint}}}{\prod_{m=1}^M P(	ext{Leg } m)}$$
- $
ho_{	ext{mult}} > 1.0$: Positive synergy parlay (underpriced by naive independent pricing).
- True Zero-Vig Fair Odds: $O_{	ext{fair}} = rac{1}{\hat{P}_{	ext{joint}}}$.
- Expected Value: $	ext{EV} = \left(\hat{P}_{	ext{joint}} \cdot O_{	ext{offered}}
ight) - 1.0$.

---

## 17. Pitch Physics, Trajectory Aerodynamics & Stuff+/Location+ Models

### 17.1 Physical Stuff+ Formulation
Isolates intrinsic physical pitch quality from defensive context and batter quality:
$$	ext{Stuff+} = 100 + 15 \cdot \left( w_v \cdot z_{	ext{velo}} + w_m \cdot z_{	ext{movement}} + w_e \cdot z_{	ext{extension}}
ight)$$
where $z_{	ext{velo}} = (v - \mu_v) / \sigma_v$, $z_{	ext{movement}}$ measures IVB / sweep relative to pitch-type baselines, and $100$ represents MLB average.

### 17.2 Location+ Command Formulation
Evaluates plate crossing coordinates $(p_x, p_z)$ relative to count-specific strategic objectives (e.g., shadow chase execution on 2-strikes vs zone competitiveness when behind).

### 17.3 Pitching+ Composite
$$	ext{Pitching+} = 0.60 \cdot 	ext{Stuff+} + 0.40 \cdot 	ext{Location+}$$

---

## 18. 2D Strike Zone Kernel Density Estimation & Ballistic Spray Kinematics

### 18.1 Bivariate Gaussian KDE Surface
$$\hat{f}(x, z) = rac{1}{2\pi N h_x h_z} \sum_{i=1}^N \exp\left( -rac{1}{2}\left[ \left(rac{x - x_i}{h_x}
ight)^2 + \left(rac{z - z_i}{h_z}
ight)^2
ight]
ight)$$
with bandwidths $h_x, h_z$ computed via Silverman's adaptive rule ($h = 1.06 \sigma N^{-1/5}$).

### 18.2 Ballistic Spray Kinematics
Translates exit velocity ($v_0$), launch angle ($	heta$), spray angle ($\phi$), and Air Density Index ($ADI$) into diamond coordinates:
$$d = \left(rac{v_0^2 \sin(2	heta)}{g}
ight) \cdot \eta_{	ext{aero}}(ADI, 	heta)$$
$$(x_{	ext{field}}, y_{	ext{field}}) = (d \sin \phi, d \cos \phi)$$

---

## 19. Hierarchical Neural Embeddings & Tree-Residual Combiners

### 19.1 Low-Dimensional Categorical Embeddings
Entities are mapped to dense latent vectors: $\mathbf{e}_p \in \mathbb{R}^{d_p}, \mathbf{e}_t \in \mathbb{R}^{d_t}, \mathbf{e}_v \in \mathbb{R}^{d_v}$.

### 19.2 Staged Boosting Residual Fusion
Combines baseline tree logit predictions with neural non-linear interaction residuals:
$$P_{	ext{composite}} = \sigma\left( 	ext{logit}(P_{	ext{tree}}) + 	ext{MLP}(\mathbf{x}_{	ext{cont}}, \mathbf{e}_{p,H}, \mathbf{e}_{p,A}, \mathbf{e}_{t,H}, \mathbf{e}_{t,A})
ight)$$
Bounded residual log-odds $\Delta \in [-1.5, +1.5]$ ensure numerical stability and preserve base tree calibration.

---

## 20. Unsupervised Player Archetypes & Mahalanobis Pitcher Similarity

### 20.1 Pitcher Physical Signature
Represents a pitcher by physical vector $\mathbf{x} = [v_{\text{FB}}, \text{IVB}_{\text{FB}}, \text{Sweep}_{\text{SL}}, \text{Drop}_{\text{CU}}, \text{Ext}]$.

### 20.2 Weighted Normalized Distance & Similarity
$$D(\mathbf{x}_{\text{target}}, \mathbf{x}_i) = \sqrt{ \sum_{j=1}^D w_j \left(\frac{x_{\text{target},j} - x_{i,j}}{\sigma_j}\right)^2 }$$
$$\text{Similarity}(\mathbf{x}_{\text{target}}, \mathbf{x}_i) = 100 \cdot \exp\left( -\frac{D(\mathbf{x}_{\text{target}}, \mathbf{x}_i)}{1.5} \right)$$

---

## 21. Live In-Game Hedging & Middle Corridor Arbitrage

### 21.1 Equal-Profit Live Hedging
Given initial stake $S_1$ at odds $O_1$ and current live opponent odds $O_2$:
$$S_2 = \frac{S_1 \cdot O_1}{O_2}$$
$$\text{Net Profit} = S_1 \cdot O_1 \left(1 - \frac{1}{O_2}\right) - S_1$$
Guaranteed positive profit exists whenever $O_2 > \frac{S_1 \cdot O_1}{S_1 \cdot O_1 - S_1} = \frac{O_1}{O_1 - 1}$.

### 21.2 Middle Corridor Discovery
For initial line $L_1$ and live opposite line $L_2$ where $L_2 > L_1$:
The discrete integer interval $\{k \in \mathbb{Z} : L_1 < k < L_2\}$ represents the middle corridor where both wagers win simultaneously.

---

## 22. Academic Bibliography & Literature Citations

1. **James, Bill** (1981). *The 1981 Baseball Abstract*. Ballantine Books. (Pythagorean Expectation and run-differential modeling).
2. **Tango, Tom; Lichtman, Mitchel; Dolphin, Andrew** (2006). *The Book: Playing the Percentages in Baseball*. Potomac Books. (Linear weights, Markov run expectancy, wOBA, and platoon leverage).
3. **Swartz, Matt; Seidman, Eric** (2010). "Skill-Interactive ERA (SIERA) Part I to V". *Baseball Prospectus*.
4. **Studeman, Dave** (2005). "xFIP: A New Approach to Pitcher Evaluation". *The Hardball Times*.
5. **Pollack, Nick; Fast, Alex** (2018). "CSW: A New Metric for Pitch Quality". *Pitcher List*.
6. **Nathan, Alan M.** (2015). "The Physics of Baseball Pitch Movement and Statcast Trajectory Analysis". *American Journal of Physics*.
7. **Silver, Nate** (2006). "PECOTA: Forecasting Major League Baseball Performance and Matchup Discrepancies". *Baseball Prospectus*.
8. **Carleton, Russell** (2015). "Pitch Type Interaction and True Talent Expectancies". *Baseball Prospectus*.
9. **Petriello, Mike; Albert, Jim; Fast, Alex** (2018). "Statcast Strike Zone Geometry & Attack Zone Topologies". *MLB Advanced Media*.
10. **Brier, Glenn W.** (1950). "Verification of Forecasts Expressed in Terms of Probability". *Monthly Weather Review*.
11. **Kelly, J. L.** (1956). "A New Interpretation of Information Rate". *Bell System Technical Journal*, 35(4), 917–926.
12. **Platt, John** (1999). "Probabilistic Outputs for Support Vector Machines and Comparisons to Regularized Likelihood Methods". *Advances in Large Margin Classifiers*.
13. **Nelsen, Roger B.** (2006). *An Introduction to Copulas*. Springer Science & Business Media. (Multivariate copulas and dependency modeling in wagering).
14. **Breiman, Leo** (1996). "Stacked Regressions". *Machine Learning*, 24(1), 49–64. (Convex non-negative ensemble meta-learning).
15. **Efron, Bradley; Morris, Carl** (1975). "Data Analysis Using Stein's Estimator and Its Generalizations". *Journal of the American Statistical Association*. (Empirical Bayes shrinkage).
16. **Fast, Mike** (2011). "Spin and Pitch Movement in PITCHf/x". *Baseball Prospectus*.
17. **Silverman, B. W.** (1986). *Density Estimation for Statistics and Data Analysis*. Chapman and Hall.
18. **Guo, Cheng; Berkhahn, Felix** (2016). "Entity Embeddings of Categorical Variables". *arXiv:1604.06737*.
19. **Mahalanobis, Prasanta Chandra** (1936). "On the Generalised Distance in Statistics". *Proceedings of the National Institute of Sciences of India*.
20. **Thorp, Edward O.** (2006). "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market". *Handbook of Asset and Liability Management*.
