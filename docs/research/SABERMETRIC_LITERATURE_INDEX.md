# Sabermetric Literature & Quantitative Research Index

This knowledge repository indexes the fundamental texts, academic papers, and sabermetric treatises that govern the formulas, physical constants, and models implemented in the MLB platform.

---

## 1. Foundational Sabermetric Treatises

### 1.1 *The Book: Playing the Percentages in Baseball*
- **Authors**: Tom Tango, Mitchel Lichtman, Andrew Dolphin (2006).
- **Key Concepts Implemented in Platform**:
  - **Chapter 1 (Linear Weights & wOBA)**: Derivation of run values for walks ($0.69$), singles ($0.88$), doubles ($1.24$), triples ($1.56$), home runs ($1.95$), and outs ($-0.27$). Implemented in `mlb_baseball/sql/team_woba_retrosheet_update.sql`.
  - **Chapter 2 (Run Expectancy Matrix & 24-State RE24)**: Base/out transition matrices and immediate run expectancies. Implemented in `mlb_baseball/model/markov/` and `mlb_baseball/sql/markov_transition_counts.sql`.
  - **Chapter 5 (Leverage Index & Win Expectancy)**: Quantifying the swing in win probability on every pitch/event. Implemented in `mlb_baseball/model/leverage.py` and `mlb_baseball/sql/team_leverage_re24_update.sql`.
  - **Chapter 6 (Times Through the Order Penalty - TTOP)**: Pitcher effectiveness decay per cycle through the batting order ($+20$ points of wOBA per cycle).
  - **Chapter 8 (The Platoon Advantage & Handedness)**: Empirical advantages of opposite-handed batter/pitcher matchups ($+15$ to $+30$ points of wOBA).

### 1.2 *Moneyball: The Art of Winning an Unfair Game*
- **Author**: Michael Lewis (2003).
- **Core Market Inefficiencies Addressed in Platform**:
  - **On-Base Percentage Over Batting Average**: Prioritizing discipline and walk rates (`bb_pct`, `o_swing_pct`, `chase_pct`) over raw batting average.
  - **Relief Pitching Arbitrage**: Modeling bullpens as pooled run-prevention units rather than valuing individual "Closers" and Save totals. Implemented in `mlb_baseball/model/bullpen.py`.
  - **Defense & Run Prevention Independence**: Decoupling defense from pitcher talent using DIPS/FIP/SIERA.

### 1.3 *The Bill James Baseball Abstract* (1981–1988)
- **Author**: Bill James.
- **Key Inventions**:
  - **Pythagorean Expectation**: Win percentage as a function of runs scored ($R$) and runs allowed ($RA$):
    $$W\% = \frac{R^{1.83}}{R^{1.83} + RA^{1.83}}$$
    Implemented in `gold.game_feature.home_pyth_wpct` and `away_pyth_wpct`.
  - **Log5 Probability Theorem**: Estimating head-to-head win probability between two teams with true talent winning percentages $P_A$ and $P_B$:
    $$P(A \text{ beats } B) = \frac{P_A - P_A P_B}{P_A + P_B - 2 P_A P_B}$$
    Implemented in `mlb_baseball/model/log5.py`.

---

## 2. Ball Flight Physics & Statcast Tracking

### 2.1 *The Physics of Baseball & Aerodynamic Pitch Movement*
- **Author**: Dr. Alan M. Nathan (Professor Emeritus of Physics, University of Illinois).
- **Core Principles**:
  - **Magnus Force & Spin Axis**: Backspin imparts upward lift; topspin imparts downward acceleration; sidespin imparts transverse deflection.
  - **Induced Vertical Break (IVB)**: Vertical deviation from a gravity-only free-fall trajectory:
    $$\text{IVB (inches)} = pfx\_z \times 12.0$$
    Implemented in `mlb_baseball/model/pitch_movement.py` and `gold.game_feature.home_starter_fastball_ivb_in`.
  - **Vertical Movement Separation ($\Delta \text{IVB}$)**: Pitch tunneling delta between primary fastball and breaking ball ($\Delta \text{IVB} = \text{IVB}_{\text{FB}} - \text{IVB}_{\text{CU}}$).

### 2.2 *Statcast Strike Zone Geometry & Attack Zone Topologies*
- **Authors**: Mike Petriello, Jim Albert, Alex Fast (MLB.com / Statcast, 2018).
- **The 4-Zone Partition**:
  1. **Heart (Zone 5)**: The middle sweet-spot ($[-0.55, 0.55]$ ft horizontal, $[1.8, 3.0]$ ft vertical).
  2. **Shadow (Zones 1-9 edges)**: The 3.3-inch boundary along the rule book strike zone.
  3. **Chase (Zones 11-14)**: The 1-2 ball-width perimeter outside the shadow zone.
  4. **Waste (Outside Chase)**: Uncompetitive out-of-zone pitches.
  Implemented in `mlb_baseball/model/command.py` and `mlb_baseball/sql/pitcher_command_update.sql`.

---

## 3. Advanced Defense, Pitch Framing & Baserunning

### 3.1 *Catcher Pitch Framing & Called Strikes Above Expected (CSAE)*
- **Authors**: Mike Fast (Baseball Prospectus, 2011); Dan Brooks & Harry Pavlidis (Pitch Info, 2014).
- **Core Methodology**:
  - Probability of a called strike conditioned on plate coordinates $(x, z)$, batter handedness, and pitch type.
  - $\text{CSAE\%} = \text{Actual Called Strikes} - \text{Expected Called Strikes}$ on Shadow pitches.
  - Run Value: $1 \text{ Extra Called Strike} \approx 0.125 \text{ Runs}$.
  - Implemented in `mlb_baseball/model/framing.py` and `transforms/models/catcher_framing_csae.sql`.

### 3.2 *Baserunning Runs (BsR = wSB + UBR)*
- **Authors**: Tom Tango; Bill James; Dan Fox (Baseball Prospectus, 2006).
- **Linear Run Weights for Stolen Bases**:
  $$\text{wSB} = \text{SB} \cdot 0.20 - \text{CS} \cdot 0.407$$
  $$\text{BsR} = \text{wSB} + \text{UBR}$$
  Implemented in `mlb_baseball/model/bsr.py` and `transforms/models/team_bsr_comprehensive.sql`.

---

## 4. Forecasting, Prediction Markets & Proper Scoring Rules

### 4.1 *Proper Scoring Rules & Brier Calibration*
- **Author**: Glenn W. Brier (1950).
- **Scoring Axioms**:
  - Model comparisons must use proper scoring rules: **Log-Loss** (Cross-Entropy) and **Brier Score**.
  - Accuracy is an improper score for probabilistic forecasts.
  - Calibration curves assess reliability across decile bins.
  - Implemented in `mlb_baseball/model/evaluation.py`.

### 4.2 *Prediction Market Alpha: Polymarket & Kalshi vs Sportsbooks*
- **Key Concepts**:
  - Event contract prices represent real-money equilibrium implied probabilities.
  - Discrepancies between model win probability $P_{\text{model}}$ and market contract price $P_{\text{market}}$ yield tradeable Expected Value ($+EV$):
    $$\text{EV} = \frac{P_{\text{model}} - P_{\text{market}}}{P_{\text{market}}}$$
  - Implemented in `mlb_baseball/model/market.py`.
