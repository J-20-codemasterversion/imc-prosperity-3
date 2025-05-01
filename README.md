# Baroque 📈
This repository contains research and algorithms for our team, Baroque, in IMC Prosperity 2025. …
## Trader Info ✨
<table align="center">
<table>
  <tr>
    <!-- Jason only -->
    <td align="center" valign="top">
      <img src="assets/jason.png" width="100" alt="Jason Li"><br/>
      <a href="https://github.com/your-github-username"><b>Jason_Li</b></a><br/>
      <a href="https://www.linkedin.com/in/yuchen-li-b98170330/">🔗 LinkedIn</a><br/>
      🔬 💻
    </td>
  </tr>
</table>

## The Competition 🏆
IMC Prosperity 2025 was an algorithmic trading competition that lasted over 15 days, with over 15000 teams and 25000 participants globally. In this challenge, we were tasked with designing trading algorithms to maximize profits across a variety of simulated products—replicating real-world opportunities such as market making, statistical arbitrage, scalping, and locational arbitrage. Each team represented a virtual “island” trading SeaShells, the in-game currency, with fictional assets like Kelp, Squid Ink, Picnic Baskets (an ETF analogue), and Volcanic Rock Vouchers (an options analogue). In addition to algorithmic trading, each round featured a manual trading challenge, which would not be elaborated upon in this repo.

## Organization 📂
This repository contains all of our code–including internal tools, research notebooks, raw data and backtesting logs, and all versions of our algorithmic trader. The repository is organized by round. Our backtester mostly remained unchanged from round 1, but we simply copied its files over to each subsequent round, so you'll find a version of that in each folder. Within each round, you can locate the algorithmic trading code we used in our final submission by looking for the latest version–for example, for round 1, we used round_1.py for our final submission. Our visualization dashboard is located in the dashboard folder.

<details>
  <summary><h1>Tools 🛠️</h1></summary>
We relied on open-source tools for visualization, which most teams did, however, given the vague guidelines on how to use them, I would explain them here. They are respectively, Backtester and Visualation, developed by jmerle.

---

## Backtester 🔙

A standalone Python backtester that powers all five rounds of IMC Prosperity 2025.  
🔗 **[View on GitHub](https://github.com/jmerle/imc-prosperity-3-backtester/tree/master)**
1. pip update/download before each round
2. test according to round or trading day
---

## Visualization 🖥️

An interactive, browser-based dashboard for exploring your P&L and order flows.  
🔗 **[Live Visualizer](https://jmerle.github.io/imc-prosperity-3-visualizer/?/visualizer)**
For visualization, remember to run the result from the logger version of the Trader Class, which would require one to use the formatting in the visualizer.py(paste the Trader Class within visualizer.py), adding the statement "# logger.flush(state=state, trader_data=trader_data, conversions=0, orders=result)" in the second last line.

Successful Implementation of visualizer would look like this:

<img width="1495" alt="截屏2025-04-30 下午10 45 45" src="https://github.com/user-attachments/assets/b0614899-e9a4-47ac-9fee-04a385f48f0b" />



<img width="1490" alt="截屏2025-04-30 下午10 46 11" src="https://github.com/user-attachments/assets/496da8cb-81fa-4c4b-8bd6-688b675eb476" />


*This allows one to check the generic trading pattern and trace back to the timestamps when a trade was triggered.*

</details>
<details>
  <summary><h1>round 1 1️⃣</h1></summary>
In round 1, we had access to three symbols: Rainforest Resin, Kelp, and Ink.
  
## Rainforest Resin 🌴

Price oscillated tightly between 9 992 and 10 008. We bought at ≤ 9 992 and sold at ≥ 10 008, at several price levels, setting position contraints at each, capturing the full 16-point swing.
![rainforest-resin-price](https://github.com/user-attachments/assets/4233ff5b-fdde-4876-90d1-9c04d85fe944)
  
## Kelp 🌿
  
Featured a wide basis spread with a drifting mid-price. We used a rolling-mean fair value over the last n timestamps (tuned in backtests) and placed symmetric bids/asks around it, profiting on mean reversion.
![kelp-price](https://github.com/user-attachments/assets/304ddf52-e485-47b6-a989-1b93bf20aa78)


## Ink 🖋️

Showed sharp "bumps" that reverted to the pre-bump level. Our tactic:

Sell at the spike peak
Buy back at the pre-bump baseline

This bump-reversion strategy added ~ 8 % to our backtest P&L.
![squid-ink-price](https://github.com/user-attachments/assets/2bce0734-aed9-449e-911a-a7d5967747e2)


</details>

<details>
  <summary><h1>round 2 2️⃣</h1></summary>

In round 2, we had access to three new symbols: **Croissants**, **Jams**, **Djembes**, plus two synthetic Picnic Baskets.

#### Croissants 🥐  
Price oscillated between **4,265** and **4,280** with surprisingly tight spreads. We quickly realized the order book depth was asymmetric, with buy-side liquidity drying up during 120k-180k timestamps. Our solution: aggressive penny-posting on the bid side while maintaining defensive asks at +4 ticks.

#### Jams 🍓  
Featured wider spreads averaging **13,400-13,420** but with brutal inventory risk. The market showed clear directional bias during European hours (80k-140k timestamps), where we systematically bought strength and sold weakness. Our VWAP deviation model captured ~90% of the mean reversion opportunities.

#### Djembes 🥁  
Most volatile among the constituents, spiking between **6,620-6,660** unpredictably. We developed a custom signal based on the coefficient of variation over 500-tick windows, which successfully predicted 73% of the larger price swings. Position limit of 60 forced us to be surgical with entry timing.

#### Picnic Basket 1 🧺  
Contains: 6 Croissants + 3 Jams + 1 Djembes  
Theoretical value calculation: `6*CP + 3*JP + 1*DP = P1_fair`  
We detected persistent mispricing in the 20-50 SeaShell range, especially when underlying vols diverged. Our edge came from using weighted mid-prices (70% bid, 30% ask) rather than simple midpoints for fair value computation.

#### Picnic Basket 2 🧺  
Contains: 4 Croissants + 2 Jams  
Simpler composition made arbitrage more reliable. The absence of Djembes reduced tracking error to <5 SeaShells. We noticed the basket traded stale during low liquidity periods (timestamps 0-30k and 180k+), creating alpha through aggressive inventory recycling.

The butterfly arbitrage strategy added ~7% to our round P&L by exploiting pricing inefficiencies between baskets and their constituents, with our edge peaking during volatility spikes when liquidity providers pulled quotes.

</details>
<details>
  <summary><h1>round 3 3️⃣</h1></summary>

In round 3, we traded **Volcanic Rock** and five **Volcanic Rock Vouchers** (call options) with different strike prices.

#### Volcanic Rock 🌋  
Price maintained a stable trading range between **9,900** and **10,100**, centered around 10,000. We observed reduced liquidity during early timestamps (0-50k), allowing for profitable market-making with wider spreads. Our strategy evolved to dynamic spread adjustments based on time of day and order book depth.

#### Voucher_9500 🎫  
Deep in-the-money option trading close to intrinsic value. During elevated volatility periods, we identified 8-12 SeaShell pricing discrepancies that provided opportunity for delta-neutral arbitrage. Strike K = 9,500 remained profitable due to its liquid market and tight bid-ask spreads.

#### Voucher_9750 🎫  
Near-ATM option with strike K = 9,750 displayed higher sensitivity to underlying price movements. Price fluctuated between 248-280 shells. We focused on theta decay exploitation while managing delta exposure through regular hedging.

#### Voucher_10000 🎫  
ATM option became the benchmark, trading actively in the 275-310 range. We established relative value trades between this and the 9750 voucher, capitalizing on implied volatility disparities across strikes.

#### Voucher_10250 🎫  
First OTM option at K = 10,250 traded with premiums ranging 160-180 shells. While we generally avoided OTM options, we occasionally entered when volatility pricing appeared mispriced relative to our forecasts.

#### Voucher_10500 🎫  
Far OTM option at K = 10,500 showed minimal trading activity, rarely exceeding 115 shells. We maintained a consistent short premium strategy with strict position limits to manage tail risk.

Following the algorithm challenge hint, we implemented a parabolic curve-fitting approach for implied volatility moneyness relationships. By plotting v_t against m_t = log(K/S_t)/sqrt(TTE), we identified arbitrage opportunities in the volatility surface. This strategy contributed ~3% to our round P&L.

</details>
<details>
  <summary><h1>round 4 4️⃣</h1></summary>
In round 4, we gained access to Magnificent Macarons, a luxury item with complex pricing dynamics.
#### Magnificent Macarons 🥐
This product traded with a 75-unit position limit and 10-unit conversion restriction. Pricing depended on multiple factors: sunlight index, sugar futures, transport costs, tariffs, and storage capacity. After analyzing historical data, we identified a critical sunlight threshold. Below this level, macaron prices would spike substantially as supply constraints kicked in.
We employed several strategies:

Sunlight Index Trading: Built a model around the sunlight threshold for entry timing
Factor Correlation: Capitalized on relationships between macarons, sugar, and shipping markets
Inventory Control: Managed the 1 SeaShell/timestamp storage cost through tactical position sizing

Standard bid-ask spreads ran 8-15 SeaShells based on market volatility. When sunlight readings dropped below our threshold, we shifted to accumulating positions ahead of anticipated price surges. Above threshold, we returned to standard market-making with symmetric quotes.

