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
Rainforest Resin 🌴
Price oscillated tightly between 9 992 and 10 008. We bought at ≤ 9 992 and sold at ≥ 10 008, capturing the full 16-point swing.
Kelp 🌿
Featured a wide basis spread with a drifting mid-price. We used a rolling-mean fair value over the last n timestamps (tuned in backtests) and placed symmetric bids/asks around it, profiting on mean reversion.
Ink 🖋️
Showed sharp "bumps" that reverted to the pre-bump level. Our tactic:

Sell at the spike peak
Buy back at the pre-bump baseline

This bump-reversion strategy added ~ 8 % to our backtest P&L.
</details>
