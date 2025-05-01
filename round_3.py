import json
import math
import numpy as np
from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
from collections import deque

class Trader:
    # Position limits
    POSITION_LIMITS = {
        "CROISSANTS": 250,
        "JAMS": 350,
        "DJEMBES": 60,
        "PICNIC_BASKET1": 60,
        "PICNIC_BASKET2": 100,
        "KELP": 50,
        "RAINFOREST_RESIN": 60,
        "SQUID_INK": 50,
        "VOLCANIC_ROCK": 400,                    # Added VOLCANIC_ROCK
        "VOLCANIC_ROCK_VOUCHER_9500": 200,       # Added vouchers
        "VOLCANIC_ROCK_VOUCHER_9750": 200,
        "VOLCANIC_ROCK_VOUCHER_10000": 200,
        "VOLCANIC_ROCK_VOUCHER_10250": 200,
        "VOLCANIC_ROCK_VOUCHER_10500": 200,
        "MAGNIFICENT_MACARONS": 75
    }
    
    # Basket compositions
    BASKET_COMPONENTS = {
        "PICNIC_BASKET1": {"CROISSANTS": 6, "JAMS": 3, "DJEMBES": 1},
        "PICNIC_BASKET2": {"CROISSANTS": 4, "JAMS": 2}
    }
    
    # Arbitrage parameters
    Z_SCORE_THRESHOLD = 0.7  # Z-score threshold for arbitrage
    VWAP_DEVIATION_THRESHOLD = 20  # Maximum allowed VWAP deviation in ticks
    MAX_TRADES_PER_WINDOW = 5  # Maximum trades per time window
    TRADE_WINDOW_SECONDS = 10  # Time window for trade limiting
    KELP_ORDERS_ENABLED = True
    # KELP parameters - from kelp&resin_works.py
    BASE_WINDOW = 20        # Reduced from 30 for faster response
    SHORT_WINDOW = 5        # Short window for detecting changes
    SHIFT_THRESHOLD = 1.2   # Reduced from 1.5 to detect shifts earlier
    MM_LEVELS = 3           # Number of market making levels
    MM_ORDER_SIZE = 5       # Increased from 3 for larger positions
    BASE_ORDER_SIZE = 15    # Increased from 10
    SHIFT_ORDER_SIZE = 25   # Increased from 15 - take advantage of shifts
    BASE_DEVIATION = 0.007  # Reduced from 0.01 - trigger trades at smaller deviations
    SHIFT_DEVIATION = 0.005 # Threshold during shifts
    PROFIT_THRESHOLD = 0.008 # Take profits at 0.8% move
    
    # SQUID_INK strategy parameters
    INK_LONG_WINDOW = 3000      # Size of long-term baseline (previous 3000 prices)
    INK_SHORT_WINDOW = 500      # Size of short-term window (current 500 prices)
    INK_BUY_THRESHOLD = 0.01    # Buy when short-term avg > long-term avg by this percentage
    INK_SELL_DROP_PCT = 0.01    # Sell when short-term avg drops from peak
    INK_POSITION_SIZE = 50      # Fixed position size for each trade

    # RAINFOREST_RESIN parameters
    BUY_THRESHOLD_RR = 9995     # Buy threshold
    SELL_THRESHOLD_RR = 10005   # Sell threshold
    ORDER_SIZE_RR = 10          # Order size for HFT
    MM_LEVELS_RR = 4            # Number of market making levels
    MM_ORDER_SIZE_RR = 3        # Market making order size
    POSITION_LIMIT_RR = 50      # Position limit for RESIN
    
    def __init__(self):
        # Initialize VWAP data for all products (including VOLCANIC_ROCK and vouchers)
        self.VWAP_DATA = {
            product: {"price_volume": 0, "volume": 0}
            for product in self.POSITION_LIMITS.keys()
        }
        
        # Initialize spread history for each basket
        self.SPREAD_HISTORY = {
            "PICNIC_BASKET1": deque(maxlen=100),
            "PICNIC_BASKET2": deque(maxlen=100)
        }
        
        # Initialize trade log for rate limiting
        self.TRADE_LOG = {
            "PICNIC_BASKET1": deque(maxlen=10),
            "PICNIC_BASKET2": deque(maxlen=10)
        }
        
        # Initialize volcanic rock configuration
        self._initialize_configuration()
        self._initialize_state_variables()
        self._initialize_history_data()
        self._initialize_products()
    
    def _initialize_configuration(self):
        """Initialize static configuration parameters"""
        # Product configuration
        self.strikes = {
            "VOLCANIC_ROCK_VOUCHER_9500": 9500,
            "VOLCANIC_ROCK_VOUCHER_9750": 9750,
            "VOLCANIC_ROCK_VOUCHER_10000": 10000,
            "VOLCANIC_ROCK_VOUCHER_10250": 10250,
            "VOLCANIC_ROCK_VOUCHER_10500": 10500
        }
        self.position_limits = {
            "VOLCANIC_ROCK": 400,
            "VOLCANIC_ROCK_VOUCHER_9500": 200,
            "VOLCANIC_ROCK_VOUCHER_9750": 200,
            "VOLCANIC_ROCK_VOUCHER_10000": 200,
            "VOLCANIC_ROCK_VOUCHER_10250": 200,
            "VOLCANIC_ROCK_VOUCHER_10500": 200
        }
        
        # Rock trading parameters
        self.min_data_points = 25  # Minimum data points before active trading
        self.volatility_window = 5  # Window for volatility trend analysis
        self.max_position_pct = 0.8  # Maximum position as percentage of limit
        self.rock_position_factor = 0.6  # Position sizing for directional ROCK trades
        
        # Time lag parameters
        self.max_lag = 40  # Maximum lag to consider (in timestamps)
        self.lag_update_frequency = 25  # Update lead-lag windows frequency
        
        # Option trading parameters - graduated approach
        self.trade_frequency = {
            "VOLCANIC_ROCK_VOUCHER_9500": 10,  # Trade very frequently
            "VOLCANIC_ROCK_VOUCHER_9750": 15,  # Trade frequently
            "VOLCANIC_ROCK_VOUCHER_10000": 20,  # Trade moderately
            "VOLCANIC_ROCK_VOUCHER_10250": 50,  # Trade occasionally
            "VOLCANIC_ROCK_VOUCHER_10500": 50   # Trade rarely
        }
        self.position_size_percent = {
            "VOLCANIC_ROCK_VOUCHER_9500": 1.0,  # Use full position limit
            "VOLCANIC_ROCK_VOUCHER_9750": 1,  # Use full position limit
            "VOLCANIC_ROCK_VOUCHER_10000": 1.0,  # Use full position limit
            "VOLCANIC_ROCK_VOUCHER_10250": 1.0,  # Use full position limit
            "VOLCANIC_ROCK_VOUCHER_10500": 0.7   # Use 70% of position limit
        }
        self.price_diff_threshold = {
            "VOLCANIC_ROCK_VOUCHER_9500": 0.04,  # 2.75% for ITM
            "VOLCANIC_ROCK_VOUCHER_9750": 0.09,   # 2.5% for slight ITM
            "VOLCANIC_ROCK_VOUCHER_10000": 0.05,   # 5% for ATM
            "VOLCANIC_ROCK_VOUCHER_10250": 0.02,   # 4% for OTM
            "VOLCANIC_ROCK_VOUCHER_10500": 0.02    # 5% for far OTM
        }
        
        # Hedging parameters
        self.hedge_ratio = 0.7  # Target hedge ratio (0.7 = 70% hedged)
        self.max_option_hedge_pct = 0.6  # Max percentage of position to hedge with any single option
        self.hedge_preference = {  # Preference order for options as hedging instruments (1 = highest)
            "VOLCANIC_ROCK_VOUCHER_9500": 5,  # Deep ITM - good delta but expensive
            "VOLCANIC_ROCK_VOUCHER_9750": 3,  # ITM - good balance
            "VOLCANIC_ROCK_VOUCHER_10000": 1,  # ATM - most liquid, best gamma exposure
            "VOLCANIC_ROCK_VOUCHER_10250": 2,  # Slight OTM - good upside leverage
            "VOLCANIC_ROCK_VOUCHER_10500": 4   # Deep OTM - cheap but low delta
        }
    
    def _initialize_state_variables(self):
        """Initialize state tracking variables"""
        self.days_to_expiry = 7  # Start with 7 days to expiry
        self.timestamp_counter = 0
    
    def _initialize_history_data(self):
        """Initialize data structures for historical data"""
        self.price_history = {}  # Store price history for all products
        self.returns_history = {}  # Store return history (percentage changes)
        self.iv_history = {}  # Store implied volatility history
        self.moneyness_history = {}  # Store moneyness values
        self.lead_lag_windows = {}  # Store optimal lead-lag windows
        self.base_iv_history = []  # Store base IV (at moneyness=0)
        self.volatility_skew_history = []  # Store volatility skew values
        self.last_trade_timestamp = {}  # Store last trade timestamp for each product
    
    def _initialize_products(self):
        """Initialize product-specific data structures"""
        for product in list(self.strikes.keys()) + ["VOLCANIC_ROCK"]:
            self.price_history[product] = []
            self.returns_history[product] = []
            self.lead_lag_windows[product] = 5  # Initial lag window estimate
            self.last_trade_timestamp[product] = 0
            if product != "VOLCANIC_ROCK":
                self.iv_history[product] = []
                self.moneyness_history[product] = []
    
    def update_vwap(self, product: str, price: int, volume: int):
        """Update VWAP for a product"""
        self.VWAP_DATA[product]["price_volume"] += price * abs(volume)
        self.VWAP_DATA[product]["volume"] += abs(volume)
    
    def get_vwap(self, product: str) -> float:
        """Get current VWAP for a product"""
        if self.VWAP_DATA[product]["volume"] == 0:
            return 0
        return self.VWAP_DATA[product]["price_volume"] / self.VWAP_DATA[product]["volume"]
    
    def can_trade(self, basket: str, timestamp: int) -> bool:
        """Check if we can trade based on rate limiting"""
        # Skip if basket not in our trade log
        if basket not in self.TRADE_LOG:
            return True
            
        recent_trades = self.TRADE_LOG[basket]
        if len(recent_trades) >= self.MAX_TRADES_PER_WINDOW:
            oldest_trade = recent_trades[0]
            if timestamp - oldest_trade < self.TRADE_WINDOW_SECONDS * 1000:  # Convert to milliseconds
                return False
        return True
    
    def log_trade(self, basket: str, timestamp: int):
        """Log a trade for rate limiting"""
        # Skip if basket not in our trade log
        if basket not in self.TRADE_LOG:
            return
            
        self.TRADE_LOG[basket].append(timestamp)
    
    # Volcanic Rock and Options Mathematical Utilities
    def norm_cdf(self, x):
        """Standard normal cumulative distribution function."""
        return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0
    
    def black_scholes_call(self, S, K, T, r, sigma):
        """Calculate call option price using Black-Scholes formula."""
        if T <= 0 or sigma <= 0:
            return max(0, S - K)
        
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        
        try:
            call_price = S * self.norm_cdf(d1) - K * math.exp(-r * T) * self.norm_cdf(d2)
            return call_price
        except:
            return max(0, S - K)  # Fall back to intrinsic value
    
    def bs_delta(self, S, K, T, r, sigma):
        """Calculate option delta using Black-Scholes formula."""
        if T <= 0 or sigma <= 0:
            return 1.0 if S > K else 0.0
        
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        
        try:
            delta = self.norm_cdf(d1)
            return delta
        except:
            return 0.5  # Default to ATM delta
    
    def bs_gamma(self, S, K, T, r, sigma):
        """Calculate option gamma using Black-Scholes formula."""
        if T <= 0 or sigma <= 0:
            return 0.0
            
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        
        try:
            gamma = math.exp(-d1**2 / 2) / (S * sigma * math.sqrt(2 * math.pi * T))
            return gamma
        except:
            return 0.0
    
    def implied_volatility(self, S, K, T, r, market_price, precision=0.0001, max_iterations=50):
        """Calculate implied volatility using bisection method."""
        if market_price <= 0 or T <= 0:
            return 0
        
        # Intrinsic value check
        intrinsic = max(0, S - K)
        if market_price <= intrinsic:
            return 0  # No time value, can't compute IV
        
        # Bisection method
        sigma_low = 0.001
        sigma_high = 5.0
        
        for i in range(max_iterations):
            sigma_mid = (sigma_low + sigma_high) / 2.0
            price = self.black_scholes_call(S, K, T, r, sigma_mid)
            
            if abs(price - market_price) < precision:
                return sigma_mid
            
            if price < market_price:
                sigma_low = sigma_mid
            else:
                sigma_high = sigma_mid
        
        return (sigma_low + sigma_high) / 2.0
    
    def calculate_moneyness(self, S, K, T):
        """Calculate moneyness (log(K/S)/sqrt(T))."""
        if T <= 0:
            return 0
        return math.log(K / S) / math.sqrt(T)
    
    def calculate_returns(self, prices):
        """Calculate percentage returns from price series."""
        if len(prices) < 2:
            return []
            
        returns = []
        for i in range(1, len(prices)):
            ret = (prices[i] - prices[i-1]) / prices[i-1] if prices[i-1] != 0 else 0
            returns.append(ret)
            
        return returns
    
    def fit_volatility_smile(self, moneyness_values, iv_values):
        """Fit a parabolic curve to moneyness vs implied volatility data."""
        # Filter out zeros and NaNs
        valid_indices = [i for i, v in enumerate(iv_values) if v > 0]
        filtered_moneyness = [moneyness_values[i] for i in valid_indices]
        filtered_iv = [iv_values[i] for i in valid_indices]
        
        if len(filtered_moneyness) < 3:
            return None  # Not enough data points for quadratic fit
        
        # Calculate polynomial coefficients (degree 2)
        n = len(filtered_moneyness)
        sum_x = sum(filtered_moneyness)
        sum_x2 = sum([x**2 for x in filtered_moneyness])
        sum_x3 = sum([x**3 for x in filtered_moneyness])
        sum_x4 = sum([x**4 for x in filtered_moneyness])
        sum_y = sum(filtered_iv)
        sum_xy = sum([filtered_moneyness[i] * filtered_iv[i] for i in range(n)])
        sum_x2y = sum([(filtered_moneyness[i]**2) * filtered_iv[i] for i in range(n)])
        
        # Matrix for polynomial regression
        try:
            # Solve system of equations for coefficients (a, b, c) in ax^2 + bx + c
            det = n*(sum_x2*sum_x4 - sum_x3*sum_x3) - sum_x*(sum_x*sum_x4 - sum_x2*sum_x3) + sum_x2*(sum_x*sum_x3 - sum_x2*sum_x2)
            if abs(det) < 1e-10:
                return None  # Matrix is singular
                
            c = (sum_y*(sum_x2*sum_x4 - sum_x3*sum_x3) - sum_x*(sum_xy*sum_x4 - sum_x2y*sum_x3) + sum_x2*(sum_xy*sum_x3 - sum_x2*sum_x2y)) / det
            b = (n*(sum_xy*sum_x4 - sum_x2y*sum_x3) - sum_y*(sum_x*sum_x4 - sum_x2*sum_x3) + sum_x2*(sum_x*sum_x2y - sum_xy*sum_x2)) / det
            a = (n*(sum_x2*sum_x2y - sum_xy*sum_x3) - sum_x*(sum_x*sum_x2y - sum_xy*sum_x2) + sum_y*(sum_x*sum_x3 - sum_x2*sum_x2)) / det
            
            coeffs = [a, b, c]
            
            # Function to get expected IV for a given moneyness
            def expected_iv(m):
                return coeffs[0] * m**2 + coeffs[1] * m + coeffs[2]
            
            # Calculate volatility skew (difference between low strike and high strike IV)
            low_moneyness = min(filtered_moneyness)
            high_moneyness = max(filtered_moneyness)
            skew = expected_iv(high_moneyness) - expected_iv(low_moneyness)
            
            return {
                'coefficients': coeffs,
                'function': expected_iv,
                'base_iv': coeffs[2],  # The constant term is the IV at moneyness = 0
                'skew': skew  # Volatility skew measurement
            }
        except:
            return None  # Error in calculation
    
    # Market Data Analysis
    def get_mid_price(self, order_depth):
        """Calculate mid price from order book."""
        if not order_depth.buy_orders and not order_depth.sell_orders:
            return None
            
        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders.keys())
        else:
            return min(order_depth.sell_orders.keys())
            
        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders.keys())
        else:
            return best_bid
            
        return (best_bid + best_ask) / 2
    
    def update_market_data(self, state):
        """Update price and IV history based on current state."""
        # Increment timestamp counter
        self.timestamp_counter += 1
        
        # Update days to expiry (assuming one day = 100,000 timestamps)
        if self.timestamp_counter % 100000 == 0:
            self.days_to_expiry -= 1
            if self.days_to_expiry <= 0:
                self.days_to_expiry = 0.01  # Avoid division by zero
        
        # Time to expiry in years
        T = self.days_to_expiry / 365.0
        
        # Get underlying price (VOLCANIC_ROCK)
        underlying_product = "VOLCANIC_ROCK"
        underlying_price = None
        
        if underlying_product in state.order_depths:
            underlying_price = self.get_mid_price(state.order_depths[underlying_product])
            
            # Update price history for underlying
            if underlying_price is not None:
                self.price_history[underlying_product].append(underlying_price)
                
                # Update returns history
                if len(self.price_history[underlying_product]) > 1:
                    last_price = self.price_history[underlying_product][-2]
                    ret = (underlying_price - last_price) / last_price if last_price != 0 else 0
                    self.returns_history[underlying_product].append(ret)
                
                # Limit history size
                if len(self.price_history[underlying_product]) > 5000:
                    self.price_history[underlying_product] = self.price_history[underlying_product][-5000:]
                    if len(self.returns_history[underlying_product]) > 4999:
                        self.returns_history[underlying_product] = self.returns_history[underlying_product][-4999:]
        
        # Skip IV calculations if no underlying price
        if underlying_price is None:
            return None
            
        # Process each voucher product
        current_moneyness = []
        current_iv = []
        
        for product, strike in self.strikes.items():
            if product in state.order_depths:
                # Get market price
                market_price = self.get_mid_price(state.order_depths[product])
                
                if market_price is not None:
                    # Update price history for product
                    self.price_history[product].append(market_price)
                    
                    # Update returns history
                    if len(self.price_history[product]) > 1:
                        last_price = self.price_history[product][-2]
                        ret = (market_price - last_price) / last_price if last_price != 0 else 0
                        self.returns_history[product].append(ret)
                    
                    # Limit history size
                    if len(self.price_history[product]) > 5000:
                        self.price_history[product] = self.price_history[product][-5000:]
                        if len(self.returns_history[product]) > 4999:
                            self.returns_history[product] = self.returns_history[product][-4999:]
                    
                    # Calculate implied volatility
                    iv = self.implied_volatility(underlying_price, strike, T, 0.0, market_price)
                    
                    # Calculate moneyness
                    moneyness = self.calculate_moneyness(underlying_price, strike, T)
                    
                    # Update IV and moneyness history
                    self.iv_history[product].append(iv)
                    self.moneyness_history[product].append(moneyness)
                    
                    # Limit history size
                    if len(self.iv_history[product]) > 5000:
                        self.iv_history[product] = self.iv_history[product][-5000:]
                        self.moneyness_history[product] = self.moneyness_history[product][-5000:]
                    
                    # Add to current data for volatility smile fitting
                    if iv > 0:
                        current_moneyness.append(moneyness)
                        current_iv.append(iv)
                    
                    # Update lead-lag window periodically
                    self._update_lag_window(product, underlying_product)
        
        # Fit volatility smile if we have enough data points
        volatility_model = None
        if len(current_moneyness) >= 3:
            volatility_model = self.fit_volatility_smile(current_moneyness, current_iv)
            
            if volatility_model:
                # Record base IV (at-the-money IV)
                self.base_iv_history.append(volatility_model['base_iv'])
                
                # Record volatility skew
                self.volatility_skew_history.append(volatility_model['skew'])
                
                # Limit history size
                if len(self.base_iv_history) > 5000:
                    self.base_iv_history = self.base_iv_history[-5000:]
                    self.volatility_skew_history = self.volatility_skew_history[-5000:]
        
        return volatility_model
    
    def _update_lag_window(self, product, underlying_product):
        """Update lead-lag window for a specific product"""
        if len(self.returns_history.get(underlying_product, [])) > self.min_data_points and len(self.returns_history.get(product, [])) > self.min_data_points:
            if self.timestamp_counter % self.lag_update_frequency == 0:
                # Calculate optimal lag more frequently as expiry approaches
                adjusted_max_lag = max(5, self.max_lag - (7 - self.days_to_expiry) * 2)
                
                # Use returns instead of prices for better correlation
                underlying_returns = self.returns_history[underlying_product]
                product_returns = self.returns_history[product]
                
                # Find optimal lag between underlying and this voucher
                self.lead_lag_windows[product] = self.find_optimal_lag(
                    underlying_returns,
                    product_returns,
                    max_lag=adjusted_max_lag
                )
    
    def find_optimal_lag(self, series_x, series_y, max_lag=20):
        """Find optimal lag between two time series using correlation."""
        if len(series_x) < max_lag + 10 or len(series_y) < max_lag + 10:
            return 5  # Default lag if not enough data
            
        best_lag = 0
        best_corr = 0
        
        for lag in range(0, max_lag + 1):
            # Calculate correlation between lagged series
            x_lagged = series_x[:(len(series_x) - lag)]
            y = series_y[lag:]
            
            # Truncate to same length
            min_len = min(len(x_lagged), len(y))
            x_lagged = x_lagged[-min_len:]
            y = y[-min_len:]
            
            # Calculate correlation
            try:
                mean_x = sum(x_lagged) / len(x_lagged)
                mean_y = sum(y) / len(y)
                
                numerator = sum([(x_lagged[i] - mean_x) * (y[i] - mean_y) for i in range(min_len)])
                denom_x = math.sqrt(sum([(x - mean_x)**2 for x in x_lagged]))
                denom_y = math.sqrt(sum([(y_val - mean_y)**2 for y_val in y]))
                
                if denom_x > 0 and denom_y > 0:
                    corr = abs(numerator / (denom_x * denom_y))
                    
                    if corr > best_corr:
                        best_corr = corr
                        best_lag = lag
            except:
                continue
                
        return best_lag
    
    # VOLCANIC_ROCK Trading Strategy (Volatility-Based)
    def analyze_volatility_trends(self):
        """Analyze trends in base IV and volatility skew."""
        if len(self.base_iv_history) < self.volatility_window:
            return None
        
        # Get recent data
        recent_base_iv = self.base_iv_history[-self.volatility_window:]
        recent_skew = self.volatility_skew_history[-self.volatility_window:]
        
        # Calculate trends (positive = rising, negative = falling)
        base_iv_trend = recent_base_iv[-1] - recent_base_iv[0]
        skew_trend = recent_skew[-1] - recent_skew[0]
        
        # Calculate average levels
        avg_base_iv = sum(recent_base_iv) / len(recent_base_iv)
        avg_skew = sum(recent_skew) / len(recent_skew)
        
        return {
            'base_iv_trend': base_iv_trend,
            'skew_trend': skew_trend,
            'avg_base_iv': avg_base_iv,
            'avg_skew': avg_skew,
            'current_base_iv': recent_base_iv[-1],
            'current_skew': recent_skew[-1]
        }
    
    def generate_trading_signal(self, volatility_analysis, underlying_price):
        """Generate trading signal for underlying based on volatility surface analysis."""
        if not volatility_analysis or underlying_price is None:
            return None
        
        # Signal strength from -1 (strong sell) to 1 (strong buy)
        signal = 0
        
        # Factors that contribute to a buy signal
        if volatility_analysis['base_iv_trend'] > 0:
            signal += 0.3 * min(1, volatility_analysis['base_iv_trend'] / 0.05)
        
        if volatility_analysis['current_skew'] > 0:
            signal += 0.2 * min(1, volatility_analysis['current_skew'] / 0.1)
        
        if volatility_analysis['skew_trend'] > 0:
            signal += 0.2 * min(1, volatility_analysis['skew_trend'] / 0.05)
        
        # Factors that contribute to a sell signal
        if volatility_analysis['base_iv_trend'] < 0:
            signal -= 0.3 * min(1, abs(volatility_analysis['base_iv_trend']) / 0.05)
        
        if volatility_analysis['current_skew'] < 0:
            signal -= 0.2 * min(1, abs(volatility_analysis['current_skew']) / 0.1)
        
        if volatility_analysis['skew_trend'] < 0:
            signal -= 0.2 * min(1, abs(volatility_analysis['skew_trend']) / 0.05)
        
        # Adjust signal strength based on days to expiry
        expiry_factor = min(1.0, self.days_to_expiry / 5)
        signal *= expiry_factor
        
        # Determine action based on signal strength
        action = None
        if signal > 0.3:
            action = "BUY"
        elif signal < -0.3:
            action = "SELL"
        
        return {
            'action': action,
            'signal_strength': signal,
            'underlying_price': underlying_price
        }
    
    def calculate_position_size(self, signal, current_position, position_limit):
        """Calculate position size based on signal strength."""
        if not signal or not signal['action']:
            return 0
            
        # Adjust max position based on days to expiry
        adjusted_limit = int(position_limit * self.max_position_pct * min(1.0, self.days_to_expiry / 4))
        
        # Calculate target position
        target_pct = abs(signal['signal_strength']) * self.rock_position_factor
        target_position = int(adjusted_limit * target_pct) * (1 if signal['action'] == "BUY" else -1)
        
        # Don't exceed position limits
        if target_position > 0:
            target_position = min(target_position, adjusted_limit - current_position)
        else:
            target_position = max(target_position, -adjusted_limit - current_position)
            
        return target_position
    
    def generate_rock_orders(self, product, action, size, order_depth):
        """Generate orders for VOLCANIC_ROCK based on trading signal."""
        orders = []
        
        if action == "BUY" and size > 0:
            if order_depth.sell_orders:
                # Sort sell orders by price (ascending)
                sorted_prices = sorted(order_depth.sell_orders.keys())
                
                remaining = size
                for price in sorted_prices:
                    # Ensure integer quantities
                    quantity = int(min(abs(order_depth.sell_orders[price]), remaining))
                    if quantity > 0:
                        orders.append(Order(product, price, quantity))
                        remaining -= quantity
                        
                        if remaining <= 0:
                            break
        
        elif action == "SELL" and size > 0:
            if order_depth.buy_orders:
                # Sort buy orders by price (descending)
                sorted_prices = sorted(order_depth.buy_orders.keys(), reverse=True)
                
                remaining = size
                for price in sorted_prices:
                    # Ensure integer quantities
                    quantity = int(min(order_depth.buy_orders[price], remaining))
                    if quantity > 0:
                        orders.append(Order(product, price, -quantity))
                        remaining -= quantity
                        
                        if remaining <= 0:
                            break
        
        return orders
    
    # Options Trading Strategy (Time Lag-Based)
    def should_trade_now(self, product):
        """Determine if enough time has passed since last trade based on graduated frequency."""
        min_timestamp_gap = self.trade_frequency.get(product, 50)
        
        time_since_last_trade = self.timestamp_counter - self.last_trade_timestamp.get(product, 0)
        
        # Adjust frequency based on days to expiry - trade more often as expiry approaches
        if self.days_to_expiry < 4:  # If less than 4 days to expiry
            min_timestamp_gap = max(5, min_timestamp_gap // 2)  # Trade at least twice as often
        
        return time_since_last_trade >= min_timestamp_gap
    
    def predict_price_movement(self, product, underlying_product):
        """Predict voucher price movement based on lagged underlying price changes."""
        lag = self.lead_lag_windows.get(product, 5)
        
        # Not enough data for prediction
        if len(self.price_history[underlying_product]) <= lag:
            return 0
        
        # Get recent underlying price changes
        recent_prices_underlying = self.price_history[underlying_product][-lag-5:]
        
        # Calculate short-term trend in underlying
        short_window = min(5, len(recent_prices_underlying))
        short_term_change = (recent_prices_underlying[-1] - recent_prices_underlying[-short_window]) / recent_prices_underlying[-short_window]
        
        # Calculate momentum in underlying
        recent_momentum = 0
        if len(self.returns_history[underlying_product]) > 5:
            recent_momentum = sum(self.returns_history[underlying_product][-5:])
        
        # Combine signals
        predicted_move = short_term_change + 0.5 * recent_momentum
        
        # Scale prediction based on strike (higher strikes are more sensitive to changes)
        strike_scaling = 1.0
        strike = self.strikes[product]
        underlying_price = self.price_history[underlying_product][-1]
        
        if strike < underlying_price:  # ITM
            strike_scaling = 0.7
        elif strike > underlying_price * 1.05:  # OTM
            strike_scaling = 1.5
        
        return predicted_move * strike_scaling
    
    def find_time_lag_opportunities(self, state, underlying_price):
        """Find trading opportunities based on time lag prediction."""
        if underlying_price is None:
            return {}
            
        opportunities = {}
        
        # Time to expiry in years
        T = self.days_to_expiry / 365.0
        
        for product, strike in self.strikes.items():
            # Skip if not in order depths or shouldn't trade now
            if product not in state.order_depths or not self.should_trade_now(product):
                continue
                
            market_price = self.get_mid_price(state.order_depths[product])
            if market_price is None:
                continue
                
            # Calculate theoretical price
            # Get implied volatility (if available)
            iv = 0.0
            if product in self.iv_history and len(self.iv_history[product]) > 0:
                iv = self.iv_history[product][-1]
                
            # If no IV available, estimate based on strike
            if iv <= 0:
                # Estimate IV based on strike distance
                strike_ratio = strike / underlying_price
                base_vol = 0.5 - (7 - self.days_to_expiry) * 0.05
                base_vol = max(0.2, min(0.5, base_vol))
                
                if strike_ratio < 0.95:  # ITM
                    iv = base_vol * 0.9
                elif strike_ratio > 1.05:  # OTM
                    iv = base_vol * 1.1
                else:  # ATM
                    iv = base_vol
            
            # Calculate theoretical price
            theo_price = self.black_scholes_call(underlying_price, strike, T, 0.0, iv)
            
            # Calculate predicted price movement based on time lag
            predicted_move = self.predict_price_movement(product, "VOLCANIC_ROCK")
            
            # Adjust theoretical price based on predicted movement
            adjusted_theo_price = theo_price * (1 + predicted_move)
            
            # Calculate price difference percentage
            price_diff_pct = (adjusted_theo_price - market_price) / market_price if market_price > 0 else 0
            
            # Check if difference exceeds threshold
            threshold = self.price_diff_threshold.get(product, 0.05)
            
            # Current position
            current_position = state.position.get(product, 0)
            position_limit = self.position_limits.get(product, 200)
            
            # Determine action
            action = None
            if abs(price_diff_pct) > threshold:
                if price_diff_pct > 0:  # Theoretical > Market
                    # Check if we can buy more
                    if current_position < position_limit * self.position_size_percent.get(product, 0.5):
                        action = "BUY"
                else:  # Market > Theoretical
                    # Check if we can sell more
                    if current_position > -position_limit * self.position_size_percent.get(product, 0.5):
                        action = "SELL"
                        
            if action:
                # Calculate position size
                max_size = position_limit * self.position_size_percent.get(product, 0.5)
                size = int(max_size * abs(price_diff_pct) * 5)  # Scale size by price difference
                size = max(5, min(size, int(max_size)))  # Between 5 and max_size
                
                # Adjust for days to expiry
                expiry_factor = max(0.3, min(1.0, self.days_to_expiry / 7.0))
                size = int(size * expiry_factor)
                
                if size >= 5:  # Minimum size check
                    opportunities[product] = {
                        'action': action,
                        'size': size,
                        'market_price': market_price,
                        'theo_price': adjusted_theo_price,
                        'price_diff_pct': price_diff_pct,
                        'order_depth': state.order_depths[product]
                    }
        
        return opportunities
    
    def find_directional_option_trades(self, state, underlying_price, rock_signal):
        """Find option trades that align with the underlying direction"""
        if underlying_price is None or rock_signal is None or not rock_signal['action']:
            return {}
                
        opportunities = {}
        rock_direction = rock_signal['action']  # "BUY" or "SELL"
        signal_strength = rock_signal['signal_strength']
        
        # Time to expiry in years
        T = self.days_to_expiry / 365.0
        
        # Select appropriate strikes based on direction
        target_strikes = []
        if rock_direction == "BUY":
            # In uptrend, focus on at-the-money and out-of-the-money options
            target_strikes = ["VOLCANIC_ROCK_VOUCHER_10000", 
                            "VOLCANIC_ROCK_VOUCHER_10250", 
                            "VOLCANIC_ROCK_VOUCHER_10500"]
        else:  # "SELL"
            # In downtrend, focus on in-the-money options
            target_strikes = ["VOLCANIC_ROCK_VOUCHER_9500", 
                            "VOLCANIC_ROCK_VOUCHER_9750", 
                            "VOLCANIC_ROCK_VOUCHER_10000"]
        
        # Process each target strike
        for product in target_strikes:
            # Skip if not in order depths or shouldn't trade now
            if product not in state.order_depths or not self.should_trade_now(product):
                continue
                
            market_price = self.get_mid_price(state.order_depths[product])
            if market_price is None:
                continue
            
            # Calculate option delta for position sizing
            iv = 0.0
            if product in self.iv_history and len(self.iv_history[product]) > 0:
                iv = self.iv_history[product][-1]
                
            # If no IV available, estimate based on strike
            if iv <= 0:
                strike_ratio = self.strikes[product] / underlying_price
                base_vol = 0.5 - (7 - self.days_to_expiry) * 0.05
                base_vol = max(0.2, min(0.5, base_vol))
                
                if strike_ratio < 0.95:  # ITM
                    iv = base_vol * 0.9
                elif strike_ratio > 1.05:  # OTM
                    iv = base_vol * 1.1
                else:  # ATM
                    iv = base_vol
                    
            # Calculate option delta
            delta = self.bs_delta(underlying_price, self.strikes[product], T, 0.0, iv)
            
            # Determine option action based on underlying direction
            option_action = None
            if rock_direction == "BUY":
                option_action = "BUY"  # Buy calls in uptrend
            else:  # rock_direction == "SELL"
                option_action = "SELL"  # Sell calls in downtrend
            
            # Current position and limits
            current_position = state.position.get(product, 0)
            position_limit = self.position_limits.get(product, 200)
            
            # Check if we can take the position
            can_execute = False
            if option_action == "BUY" and current_position < position_limit * self.position_size_percent.get(product, 0.5):
                can_execute = True
            elif option_action == "SELL" and current_position > -position_limit * self.position_size_percent.get(product, 0.5):
                can_execute = True
            
            if can_execute:
                # Calculate position size based on rock signal strength and option delta
                size_factor = min(1.0, abs(signal_strength) * 2)  # Scale by signal strength
                
                # Adjust size based on delta - use smaller size for low-delta options
                delta_factor = min(1.0, delta * 2)  # Full size for delta >= 0.5, scaled down for lower deltas
                
                max_size = position_limit * self.position_size_percent.get(product, 0.5) * size_factor * delta_factor
                
                # Adjust for days to expiry
                expiry_factor = max(0.3, min(1.0, self.days_to_expiry / 7.0))
                size = int(max_size * expiry_factor)
                
                # Ensure minimum size
                if size >= 5:
                    opportunities[product] = {
                        'action': option_action,
                        'size': size,
                        'market_price': market_price,
                        'order_depth': state.order_depths[product],
                        'reason': f"Aligned with {rock_direction} signal for underlying"
                    }
        
        return opportunities
    
    def _execute_rock_strategy(self, state, underlying_price, volatility_model):
        """Execute trading strategy for VOLCANIC_ROCK."""
        underlying_product = "VOLCANIC_ROCK"
        underlying_position = state.position.get(underlying_product, 0)
        
        # Generate directional trading signal for underlying
        volatility_analysis = self.analyze_volatility_trends()
        signal = self.generate_trading_signal(volatility_analysis, underlying_price)
        
        if signal and signal['action']:
            # Calculate position change based on signal
            position_change = self.calculate_position_size(
                signal,
                underlying_position,
                self.position_limits[underlying_product]
            )
            
            if abs(position_change) >= 10:  # Only trade if change is significant
                # Generate orders for VOLCANIC_ROCK
                action = signal['action']
                size = abs(position_change)
                
                rock_orders = self.generate_rock_orders(
                    underlying_product,
                    action,
                    size,
                    state.order_depths[underlying_product]
                )
                
                return rock_orders
        
        return None
    
    def _execute_option_strategy(self, state, underlying_price):
        """Execute trading strategy for options."""
        option_orders = {}
        
        # Find option opportunities based on time lag
        option_opportunities = self.find_time_lag_opportunities(state, underlying_price)
        
        # Generate orders for each opportunity
        for product, opportunity in option_opportunities.items():
            orders = self.generate_option_orders(product, opportunity)
            
            if orders:
                option_orders[product] = orders
        
        return option_orders
    
    def generate_option_orders(self, product, opportunity):
        """Generate orders for options based on time-lag prediction or directional alignment."""
        orders = []
        
        action = opportunity['action']
        size = opportunity['size']
        order_depth = opportunity['order_depth']
        
        # Update last trade timestamp
        self.last_trade_timestamp[product] = self.timestamp_counter
        
        if action == "BUY":
            if order_depth.sell_orders:
                # Sort sell orders by price (ascending)
                sorted_prices = sorted(order_depth.sell_orders.keys())
                
                remaining = size
                for price in sorted_prices:
                    # Ensure integer quantities
                    quantity = int(min(abs(order_depth.sell_orders[price]), remaining))
                    if quantity > 0:
                        orders.append(Order(product, price, quantity))
                        remaining -= quantity
                        
                        if remaining <= 0:
                            break
        
        elif action == "SELL":
            if order_depth.buy_orders:
                # Sort buy orders by price (descending)
                sorted_prices = sorted(order_depth.buy_orders.keys(), reverse=True)
                
                remaining = size
                for price in sorted_prices:
                    # Ensure integer quantities
                    quantity = int(min(order_depth.buy_orders[price], remaining))
                    if quantity > 0:
                        orders.append(Order(product, price, -quantity))
                        remaining -= quantity
                        
                        if remaining <= 0:
                            break
        
        return orders

    def run(self, state: TradingState) -> tuple[Dict[str, List[Order]], int, str]:
        
        # Initialize result dictionary and conversions
        result = {}
        conversions = 0
        
        # Ensure position limits contains all products in order_depths
        for product in state.order_depths:
            result[product] = []
        
        # Initialize or load trader data
        if state.traderData and state.traderData != "":
            try:
                trader_data = json.loads(state.traderData)
            except:
                trader_data = {
                    'price_history': {},
                    'fair_values': {},
                    'basket_spreads': {},
                    'kelp_data': {'price_history': [], 'base_levels': [], 'last_base': None, 'entry_prices': {}, 'in_shift': False, 'shift_direction': 0},
                    'squid_ink': {
                        'price_history': [],
                        'short_ma': [],
                        'long_ma': [],
                        'rsi': 50,
                        'last_signal': 'none',
                        'last_price': 0,
                        'squid_peak_data': {
                            'in_peak': False,
                            'in_short': False,
                            'entry_mode': False,
                            'exit_mode': False,
                            'peak_start_price': 0,
                            'peak_start_idx': 0,
                            'highest_short_avg': 0,
                            'exclude_until_idx': 0,
                            'target_position': 0
                        }
                    },
                    'resin': {'price_history': []}
                }
        else:
            trader_data = {
                'price_history': {},
                'fair_values': {},
                'basket_spreads': {},
                'kelp_data': {'price_history': [], 'base_levels': [], 'last_base': None, 'entry_prices': {}, 'in_shift': False, 'shift_direction': 0},
                'squid_ink': {
                    'price_history': [],
                    'short_ma': [],
                    'long_ma': [],
                    'rsi': 50,
                    'last_signal': 'none',
                    'last_price': 0,
                    'squid_peak_data': {
                        'in_peak': False,
                        'in_short': False,
                        'entry_mode': False,
                        'exit_mode': False,
                        'peak_start_price': 0,
                        'peak_start_idx': 0,
                        'highest_short_avg': 0,
                        'exclude_until_idx': 0,
                        'target_position': 0
                    }
                },
                'resin': {'price_history': []}
            }
        
        # Make sure squid_peak_data is properly initialized
        if 'squid_ink' not in trader_data:
            trader_data['squid_ink'] = {
                'price_history': [],
                'short_ma': [],
                'long_ma': [],
                'rsi': 50,
                'last_signal': 'none',
                'last_price': 0
            }
        
        if 'squid_peak_data' not in trader_data['squid_ink']:
            trader_data['squid_ink']['squid_peak_data'] = {
                'in_peak': False,
                'in_short': False,
                'entry_mode': False,
                'exit_mode': False,
                'peak_start_price': 0,
                'peak_start_idx': 0,
                'highest_short_avg': 0,
                'exclude_until_idx': 0,
                'target_position': 0
            }
        
        # Get current positions safely
        positions = {}
        for product in state.position:
            positions[product] = state.position[product]
        
        # Initialize price history for all products in order_depths
        for product in state.order_depths:
            if product not in trader_data['price_history']:
                trader_data['price_history'][product] = []
                
        # Also initialize for products in POSITION_LIMITS
        for product in self.POSITION_LIMITS.keys():
            if product not in trader_data['price_history']:
                trader_data['price_history'][product] = []
        
        # Calculate mid prices for all products
        mid_prices = {}
        for product in state.order_depths:
            order_depth = state.order_depths[product]
            if order_depth.sell_orders and order_depth.buy_orders:
                best_ask = min(order_depth.sell_orders.keys())
                best_bid = max(order_depth.buy_orders.keys())
                mid_prices[product] = (best_ask + best_bid) / 2
                
                # Update price history
                trader_data['price_history'][product].append(mid_prices[product])
                if len(trader_data['price_history'][product]) > 100:
                    trader_data['price_history'][product] = trader_data['price_history'][product][-100:]
        
        # Get current positions safely
        positions = {}
        for product in state.position:
            positions[product] = state.position[product]
        
        # Calculate mid prices and update VWAP for all products
        mid_prices = {}
        for product in state.order_depths:
            order_depth = state.order_depths[product]
            if order_depth.sell_orders and order_depth.buy_orders:
                best_ask = min(order_depth.sell_orders.keys())
                best_bid = max(order_depth.buy_orders.keys())
                mid_prices[product] = (best_ask + best_bid) / 2
                
                # Update VWAP with current trades
                for price, volume in order_depth.sell_orders.items():
                    self.update_vwap(product, price, volume)
                for price, volume in order_depth.buy_orders.items():
                    self.update_vwap(product, price, volume)
        
        # Calculate fair values for baskets based on component prices
        fair_values = {}
        for basket, components in self.BASKET_COMPONENTS.items():
            basket_value = 0
            all_components_priced = True
            
            for comp, count in components.items():
                if comp in mid_prices:
                    basket_value += mid_prices[comp] * count
                else:
                    all_components_priced = False
                    break
            
            if all_components_priced:
                fair_values[basket] = basket_value
        
        # Process each basket for arbitrage opportunities
        for basket in self.BASKET_COMPONENTS:
            # Skip if basket not in order books or fair values
            if basket not in state.order_depths or basket not in fair_values:
                continue
            
            # Get order depth and position for current basket
            order_depth = state.order_depths[basket]
            basket_position = positions.get(basket, 0)
            
            # Skip if no orders on both sides
            if not order_depth.sell_orders or not order_depth.buy_orders:
                continue
            
            # Get best bid and ask for basket
            best_basket_bid = max(order_depth.buy_orders.keys())
            best_basket_ask = min(order_depth.sell_orders.keys())
            
            # Get fair value and calculate arbitrage metrics
            fair_value = fair_values[basket]
            basket_bid_vs_fair = best_basket_bid - fair_value
            basket_ask_vs_fair = best_basket_ask - fair_value
            
            # Calculate spread and update history
            spread = best_basket_bid - fair_value
            self.SPREAD_HISTORY[basket].append(spread)
            
            # Calculate Z-score if we have enough history
            if len(self.SPREAD_HISTORY[basket]) >= 30:
                mean = np.mean(self.SPREAD_HISTORY[basket])
                std = np.std(self.SPREAD_HISTORY[basket])
                z_score = (spread - mean) / std if std > 0 else 0
            else:
                z_score = 0
            
            # Get VWAP and calculate deviation
            vwap = self.get_vwap(basket)
            vwap_deviation = mid_prices.get(basket, 0) - vwap
            
            # Get component positions
            component_positions = {comp: positions.get(comp, 0) for comp in self.BASKET_COMPONENTS[basket]}
            
            # Calculate maximum potential arbitrage size based on position limits
            max_basket_buy = self.POSITION_LIMITS.get(basket, 100) - basket_position
            max_basket_sell = self.POSITION_LIMITS.get(basket, 100) + basket_position
            
            # Check component position limits for each direction
            max_component_buy = {}
            max_component_sell = {}
            
            for comp, count in self.BASKET_COMPONENTS[basket].items():
                comp_position = component_positions.get(comp, 0)
                comp_limit = self.POSITION_LIMITS.get(comp, 100)
                max_component_buy[comp] = (comp_limit - comp_position) // count
                max_component_sell[comp] = (comp_limit + comp_position) // count
            
            # Check if we can trade based on rate limiting
            if not self.can_trade(basket, state.timestamp):
                continue
            
            # Case 1: Basket is OVERPRICED (sell basket, buy components)
            if z_score > self.Z_SCORE_THRESHOLD and abs(vwap_deviation) < self.VWAP_DEVIATION_THRESHOLD:
                # Calculate arbitrage capacity
                arb_capacity = min(
                    max_basket_sell,
                    min([max_component_buy.get(comp, 0) for comp in self.BASKET_COMPONENTS[basket]]),
                    order_depth.buy_orders[best_basket_bid]
                )
                
                if arb_capacity > 0:
                    # Check if we can get all necessary components
                    can_get_components = True
                    component_orders = {}
                    
                    for comp, count in self.BASKET_COMPONENTS[basket].items():
                        if comp not in state.order_depths or not state.order_depths[comp].sell_orders:
                            can_get_components = False
                            break
                        
                        comp_position = component_positions.get(comp, 0)
                        comp_needed = count * arb_capacity
                        
                        # Skip if we already have enough
                        if comp_position >= comp_needed:
                            continue
                        
                        # Calculate how many we need to buy
                        comp_deficit = comp_needed - comp_position
                        
                        # Check if we can buy enough
                        comp_depth = state.order_depths[comp]
                        available = sum(-vol for vol in comp_depth.sell_orders.values())
                        if available < comp_deficit:
                            can_get_components = False
                            break
                        
                        # Store orders to place
                        best_comp_ask = min(comp_depth.sell_orders.keys())
                        comp_ask_vol = -comp_depth.sell_orders[best_comp_ask]
                        buy_amount = min(comp_deficit, comp_ask_vol)
                        component_orders[comp] = (best_comp_ask, buy_amount)
                    
                    if can_get_components:
                        # First buy components
                        for comp, (price, amount) in component_orders.items():
                            if amount > 0:
                                result[comp].append(Order(comp, price, amount))
                        
                        # Then sell the basket
                        result[basket].append(Order(basket, best_basket_bid, -arb_capacity))
                        
                        # Log the trade and set conversion
                        self.log_trade(basket, state.timestamp)
                        if conversions == 0:
                            conversions = arb_capacity
            
            # Case 2: Basket is UNDERPRICED (buy basket, sell components)
            elif z_score < -self.Z_SCORE_THRESHOLD and abs(vwap_deviation) < self.VWAP_DEVIATION_THRESHOLD:
                # Calculate arbitrage capacity
                arb_capacity = min(
                    max_basket_buy,
                    min([max_component_sell.get(comp, 0) for comp in self.BASKET_COMPONENTS[basket]]),
                    -order_depth.sell_orders[best_basket_ask]
                )
                
                if arb_capacity > 0:
                    # Check if we can sell all components
                    can_sell_components = True
                    component_orders = {}
                    
                    for comp, count in self.BASKET_COMPONENTS[basket].items():
                        if comp not in state.order_depths or not state.order_depths[comp].buy_orders:
                            can_sell_components = False
                            break
                        
                        comp_position = component_positions.get(comp, 0)
                        comp_to_sell = count * arb_capacity
                        
                        # Check if we need to sell more than we have
                        comp_deficit = comp_to_sell - comp_position
                        
                        # Check if shorting is needed and possible
                        if comp_deficit > 0:
                            comp_depth = state.order_depths[comp]
                            available = sum(vol for vol in comp_depth.buy_orders.values())
                            if available < comp_deficit:
                                can_sell_components = False
                                break
                        
                        # Store orders to place
                        best_comp_bid = max(state.order_depths[comp].buy_orders.keys())
                        comp_bid_vol = state.order_depths[comp].buy_orders[best_comp_bid]
                        sell_amount = min(comp_to_sell, comp_bid_vol)
                        component_orders[comp] = (best_comp_bid, sell_amount)
                    
                    if can_sell_components:
                        # First buy the basket
                        result[basket].append(Order(basket, best_basket_ask, arb_capacity))
                        
                        # Then sell the components
                        for comp, (price, amount) in component_orders.items():
                            if amount > 0:
                                result[comp].append(Order(comp, price, -amount))
                        
                        # Log the trade and set conversion
                        self.log_trade(basket, state.timestamp)
                        if conversions == 0:
                            conversions = -arb_capacity
            
            # Dynamic market making when no arbitrage found
            elif basket in ["PICNIC_BASKET1", "PICNIC_BASKET2"] and fair_value > 0:
                # Calculate dynamic spread based on volatility
                if len(self.SPREAD_HISTORY[basket]) >= 30:
                    spread = int(max(5, np.std(self.SPREAD_HISTORY[basket]) * 2))
                else:
                    spread = 100  # Default spread
                
                buy_price = int(fair_value - spread)
                sell_price = int(fair_value + spread)
                
                # Add market making orders
                if buy_price > 0 and max_basket_buy > 0:
                    result[basket].append(Order(basket, buy_price, 1))
                
                if sell_price > 0 and max_basket_sell > 0:
                    result[basket].append(Order(basket, sell_price, -1))
        
        # Process KELP with the base level strategy
        if self.KELP_ORDERS_ENABLED and "KELP" in state.order_depths:
            product = "KELP"
            order_depth = state.order_depths[product]
            kelp_position = positions.get(product, 0)
            
            # Initialize entry price tracking if needed
            if 'entry_prices' not in trader_data['kelp_data']:
                trader_data['kelp_data']['entry_prices'] = {}
            if product not in trader_data['kelp_data']['entry_prices']:
                trader_data['kelp_data']['entry_prices'][product] = {'price': 0, 'position': 0}
            
            # Initialize orders for this product
            if product not in result:
                result[product] = []
            
            if order_depth.sell_orders and order_depth.buy_orders:
                # Get market data
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                mid_price = float((best_bid + best_ask) / 2)
                spread = best_ask - best_bid
                
                # Update price history
                trader_data['kelp_data']['price_history'].append(mid_price)
                if len(trader_data['kelp_data']['price_history']) > 1000:  # Keep reasonable history
                    trader_data['kelp_data']['price_history'] = trader_data['kelp_data']['price_history'][-1000:]
                
                # Check if we have enough data to proceed
                if len(trader_data['kelp_data']['price_history']) >= self.BASE_WINDOW:
                    # Calculate base level (longer window)
                    base_prices = trader_data['kelp_data']['price_history'][-self.BASE_WINDOW:]
                    current_base = float(np.mean(base_prices))
                    base_std = float(np.std(base_prices))
                    
                    # Calculate short-term level
                    short_window = min(self.SHORT_WINDOW, len(trader_data['kelp_data']['price_history']))
                    short_prices = trader_data['kelp_data']['price_history'][-short_window:]
                    short_level = float(np.mean(short_prices))
                    
                    # Short-term momentum
                    momentum = 0
                    if len(trader_data['kelp_data']['price_history']) >= 3:
                        price_diffs = [
                            trader_data['kelp_data']['price_history'][-i] - trader_data['kelp_data']['price_history'][-i-1] 
                            for i in range(1, 3)
                        ]
                        momentum = sum(price_diffs) / len(price_diffs)
                    
                    # Update base level history
                    trader_data['kelp_data']['base_levels'].append(current_base)
                    if len(trader_data['kelp_data']['base_levels']) > 100:
                        trader_data['kelp_data']['base_levels'] = trader_data['kelp_data']['base_levels'][-100:]
                    
                    # Detect base level shifts
                    base_shifted = False
                    shift_direction = 0  # 0=no shift, 1=up, -1=down
                    
                    # Only detect shifts if we have a last_base to compare to
                    if trader_data['kelp_data']['last_base'] is not None:
                        # Calculate how much the base has changed
                        base_change = current_base - trader_data['kelp_data']['last_base']
                        normalized_change = base_change / base_std if base_std > 0 else 0
                        
                        # Detect significant shifts
                        if abs(normalized_change) > self.SHIFT_THRESHOLD:
                            base_shifted = True
                            shift_direction = 1 if normalized_change > 0 else -1
                            trader_data['kelp_data']['in_shift'] = True
                            trader_data['kelp_data']['shift_direction'] = shift_direction
                        elif trader_data['kelp_data']['in_shift']:
                            # Check if shift has completed (base stabilized)
                            if abs(normalized_change) < 0.3:  # Shift has settled
                                trader_data['kelp_data']['in_shift'] = False
                                trader_data['kelp_data']['shift_direction'] = 0
                    
                    # Update last_base
                    trader_data['kelp_data']['last_base'] = current_base
                    
                    # Track entry prices for profit taking
                    entry_data = trader_data['kelp_data']['entry_prices'][product]
                    if kelp_position != entry_data['position']:
                        # Position has changed
                        if entry_data['position'] == 0 or (kelp_position > 0 and entry_data['position'] < 0) or (kelp_position < 0 and entry_data['position'] > 0):
                            # New position or direction change - reset entry price
                            entry_data = {'price': mid_price, 'position': kelp_position}
                        else:
                            # Update average entry price with additional position
                            # (This is approximate since we don't know exact fill prices)
                            position_change = kelp_position - entry_data['position']
                            # Only update if not close to zero (avoid division issues)
                            if abs(kelp_position) > 1:
                                if position_change > 0:  # Added to position
                                    entry_data['price'] = ((entry_data['price'] * entry_data['position']) + (mid_price * position_change)) / kelp_position
                                entry_data['position'] = kelp_position
                    
                    trader_data['kelp_data']['entry_prices'][product] = entry_data
                    
                    # Calculate price deviation from base
                    price_deviation = (mid_price - current_base) / current_base
                    
                    # PROFIT TAKING - Check if we should take profits on existing position
                    if kelp_position > 5 and entry_data['price'] > 0:
                        # We have a long position - check if price moved up enough to take profits
                        profit_pct = (mid_price - entry_data['price']) / entry_data['price']
                        if profit_pct > self.PROFIT_THRESHOLD:
                            # Take profits on 70% of position
                            take_profit_size = int(kelp_position * 0.7)
                            take_profit_size = min(take_profit_size, order_depth.buy_orders[best_bid])
                            if take_profit_size > 0:
                                result[product].append(Order(product, best_bid, -take_profit_size))
                                kelp_position -= take_profit_size
                    
                    elif kelp_position < -5 and entry_data['price'] > 0:
                        # We have a short position - check if price moved down enough to take profits
                        profit_pct = (entry_data['price'] - mid_price) / entry_data['price']
                        if profit_pct > self.PROFIT_THRESHOLD:
                            # Take profits on 70% of position
                            take_profit_size = int(abs(kelp_position) * 0.7)
                            take_profit_size = min(take_profit_size, -order_depth.sell_orders[best_ask])
                            if take_profit_size > 0:
                                result[product].append(Order(product, best_ask, take_profit_size))
                                kelp_position += take_profit_size
                    
                    # Set dynamic thresholds based on current state
                    # Default thresholds
                    buy_threshold = current_base * (1 - self.BASE_DEVIATION)
                    sell_threshold = current_base * (1 + self.BASE_DEVIATION)
                    
                    # Position bias adjustment
                    position_ratio = kelp_position / self.POSITION_LIMITS["KELP"]
                    if position_ratio > 0.3:  # Significant long position
                        # Make it harder to buy more, easier to sell
                        buy_threshold *= 0.995
                        sell_threshold *= 0.995
                    elif position_ratio < -0.3:  # Significant short position
                        # Make it harder to sell more, easier to buy
                        buy_threshold *= 1.005
                        sell_threshold *= 1.005
                    
                    # Base shift adjustment - more aggressive during shifts
                    if trader_data['kelp_data']['in_shift']:
                        shift_dir = trader_data['kelp_data']['shift_direction']
                        if shift_dir > 0:  # Base shifting up
                            # Be more aggressive buying
                            buy_threshold = current_base * (1 - self.SHIFT_DEVIATION)
                            # Don't sell unless clearly above new level
                            sell_threshold = current_base * (1 + self.SHIFT_DEVIATION * 1.5)
                        elif shift_dir < 0:  # Base shifting down
                            # Be more aggressive selling
                            sell_threshold = current_base * (1 + self.SHIFT_DEVIATION)
                            # Don't buy unless clearly below new level
                            buy_threshold = current_base * (1 - self.SHIFT_DEVIATION * 1.5)
                    
                    # Capacity calculations
                    remaining_buy_capacity = self.POSITION_LIMITS["KELP"] - kelp_position
                    remaining_sell_capacity = self.POSITION_LIMITS["KELP"] + kelp_position
                    
                    # AGGRESSIVE BUYING when price is below threshold
                    if (mid_price <= buy_threshold or (momentum < -0.5 and mid_price <= current_base * 0.997)) and remaining_buy_capacity > 0:
                        # Always market buy with aggressive size during shifts for maximum profit
                        if trader_data['kelp_data']['in_shift'] and trader_data['kelp_data']['shift_direction'] < 0:
                            # Base shifting down, buy aggressively at bottom
                            buy_size = min(self.SHIFT_ORDER_SIZE, -order_depth.sell_orders[best_ask], remaining_buy_capacity)
                            if buy_size > 0:
                                result[product].append(Order(product, best_ask, buy_size))
                                kelp_position += buy_size
                                remaining_buy_capacity -= buy_size
                        else:
                            # Normal opportunistic buying
                            order_size = self.SHIFT_ORDER_SIZE if trader_data['kelp_data']['in_shift'] else self.BASE_ORDER_SIZE
                            buy_size = min(order_size, -order_depth.sell_orders[best_ask], remaining_buy_capacity)
                            
                            if buy_size > 0:
                                result[product].append(Order(product, best_ask, buy_size))
                                kelp_position += buy_size
                                remaining_buy_capacity -= buy_size
                    
                    # AGGRESSIVE SELLING when price is above threshold
                    if (mid_price >= sell_threshold or (momentum > 0.5 and mid_price >= current_base * 1.003)) and remaining_sell_capacity > 0:
                        # Always market sell with aggressive size during shifts for maximum profit
                        if trader_data['kelp_data']['in_shift'] and trader_data['kelp_data']['shift_direction'] > 0:
                            # Base shifting up, sell aggressively at top
                            sell_size = min(self.SHIFT_ORDER_SIZE, order_depth.buy_orders[best_bid], remaining_sell_capacity)
                            if sell_size > 0:
                                result[product].append(Order(product, best_bid, -sell_size))
                                kelp_position -= sell_size
                                remaining_sell_capacity -= sell_size
                        else:
                            # Normal opportunistic selling
                            order_size = self.SHIFT_ORDER_SIZE if trader_data['kelp_data']['in_shift'] else self.BASE_ORDER_SIZE
                            sell_size = min(order_size, order_depth.buy_orders[best_bid], remaining_sell_capacity)
                            
                            if sell_size > 0:
                                result[product].append(Order(product, best_bid, -sell_size))
                                kelp_position -= sell_size
                                remaining_sell_capacity -= sell_size
                    
                    # If base is shifting, aggressively position in the direction of the shift
                    if trader_data['kelp_data']['in_shift']:
                        shift_dir = trader_data['kelp_data']['shift_direction']
                        
                        if shift_dir > 0 and kelp_position < 0:  # Base shifting up, we're short
                            # First cover all shorts
                            cover_size = min(-kelp_position, -order_depth.sell_orders[best_ask])
                            if cover_size > 0:
                                result[product].append(Order(product, best_ask, cover_size))
                                kelp_position += cover_size
                                remaining_buy_capacity -= cover_size
                            
                            # Then go long if we have capacity
                            if remaining_buy_capacity > 0:
                                long_size = min(self.SHIFT_ORDER_SIZE, -order_depth.sell_orders[best_ask], remaining_buy_capacity)
                                if long_size > 0:
                                    result[product].append(Order(product, best_ask, long_size))
                                    kelp_position += long_size
                        
                        elif shift_dir < 0 and kelp_position > 0:  # Base shifting down, we're long
                            # First reduce all longs
                            reduce_size = min(kelp_position, order_depth.buy_orders[best_bid])
                            if reduce_size > 0:
                                result[product].append(Order(product, best_bid, -reduce_size))
                                kelp_position -= reduce_size
                                remaining_sell_capacity -= reduce_size
                            
                            # Then go short if we have capacity
                            if remaining_sell_capacity > 0:
                                short_size = min(self.SHIFT_ORDER_SIZE, order_depth.buy_orders[best_bid], remaining_sell_capacity)
                                if short_size > 0:
                                    result[product].append(Order(product, best_bid, -short_size))
                                    kelp_position -= short_size
                    
                    # Market making around current base level - only if not in a shift
                    if not trader_data['kelp_data']['in_shift']:
                        # Calculate reasonable bid-ask levels around current_base
                        mm_spread = max(spread * 0.8, 4)  # At least 4 ticks or 80% of current spread
                        spread_increment = mm_spread / (self.MM_LEVELS + 1)
                        
                        # Create buy levels below current_base
                        for i in range(1, self.MM_LEVELS + 1):
                            mm_buy_price = int(current_base - (i * spread_increment))
                            # Only place if below market and we have capacity
                            if mm_buy_price < best_ask and remaining_buy_capacity >= self.MM_ORDER_SIZE:
                                result[product].append(Order(product, mm_buy_price, self.MM_ORDER_SIZE))
                                remaining_buy_capacity -= self.MM_ORDER_SIZE
                        
                        # Create sell levels above current_base
                        for i in range(1, self.MM_LEVELS + 1):
                            mm_sell_price = int(current_base + (i * spread_increment))
                            # Only place if above market and we have capacity
                            if mm_sell_price > best_bid and remaining_sell_capacity >= self.MM_ORDER_SIZE:
                                result[product].append(Order(product, mm_sell_price, -self.MM_ORDER_SIZE))
                                remaining_sell_capacity -= self.MM_ORDER_SIZE
                                
                    # Always have at least one order in book to capture extreme moves
                    if remaining_buy_capacity >= 5:
                        backstop_buy_price = int(current_base * 0.985)  # 1.5% below base
                        if backstop_buy_price < best_ask:
                            result[product].append(Order(product, backstop_buy_price, 5))
                    
                    if remaining_sell_capacity >= 5:
                        backstop_sell_price = int(current_base * 1.015)  # 1.5% above base
                        if backstop_sell_price > best_bid:
                            result[product].append(Order(product, backstop_sell_price, -5))
        
        # Process RAINFOREST_RESIN strategy
        if "RAINFOREST_RESIN" in state.order_depths:
            resin_orders = []
            resin_position = positions.get("RAINFOREST_RESIN", 0)
            order_depth = state.order_depths["RAINFOREST_RESIN"]
            
            # Check recent trades to determine last action
            last_action_was_buy = False
            last_action_was_sell = False
            
            if "RAINFOREST_RESIN" in state.own_trades and state.own_trades["RAINFOREST_RESIN"]:
                for trade in state.own_trades["RAINFOREST_RESIN"]:
                    if trade.buyer == "SUBMISSION":  # We were the buyer
                        last_action_was_buy = True
                        last_action_was_sell = False
                    elif trade.seller == "SUBMISSION":  # We were the seller
                        last_action_was_buy = False
                        last_action_was_sell = True
            
            # Update price history
            if order_depth.sell_orders and order_depth.buy_orders:
                best_ask, _ = list(order_depth.sell_orders.items())[0]
                best_bid, _ = list(order_depth.buy_orders.items())[0]
                current_mid = (best_bid + best_ask) / 2.0
                
                # Make sure resin data is initialized
                if 'resin' not in trader_data:
                    trader_data['resin'] = {'price_history': []}
                
                trader_data['resin']['price_history'].append(current_mid)
                if len(trader_data['resin']['price_history']) > 100:
                    trader_data['resin']['price_history'] = trader_data['resin']['price_history'][-100:]
            
                # Set dynamic thresholds based on recent history
                if len(trader_data['resin']['price_history']) >= 10:
                    recent_prices = np.array(trader_data['resin']['price_history'][-10:])
                    min_recent = np.min(recent_prices)
                    max_recent = np.max(recent_prices)
                    
                    if resin_position > 0:
                        buy_threshold = min_recent - 0.5
                        sell_threshold = 10000
                    elif resin_position < 0:
                        buy_threshold = 10000
                        sell_threshold = max_recent + 0.5
                    else:
                        buy_threshold = 9997
                        sell_threshold = 10003
                else:
                    buy_threshold = 9997
                    sell_threshold = 10003
                
                # Buy side processing
                remaining_buy_capacity = self.POSITION_LIMIT_RR - resin_position
                if remaining_buy_capacity > 0:
                    for ask_price, ask_volume in order_depth.sell_orders.items():
                        if ask_price <= buy_threshold:
                            vol_to_buy = min(-ask_volume, remaining_buy_capacity, self.ORDER_SIZE_RR)
                            if vol_to_buy > 0:
                                resin_orders.append(Order("RAINFOREST_RESIN", ask_price, vol_to_buy))
                                resin_position += vol_to_buy
                                remaining_buy_capacity -= vol_to_buy
                
                # Sell side processing
                remaining_sell_capacity = self.POSITION_LIMIT_RR + resin_position
                if remaining_sell_capacity > 0:
                    for bid_price, bid_volume in order_depth.buy_orders.items():
                        if bid_price >= sell_threshold:
                            vol_to_sell = min(bid_volume, remaining_sell_capacity, self.ORDER_SIZE_RR)
                            if vol_to_sell > 0:
                                resin_orders.append(Order("RAINFOREST_RESIN", bid_price, -vol_to_sell))
                                resin_position -= vol_to_sell
                                remaining_sell_capacity -= vol_to_sell
                
                # Enhanced market making with more levels
                # Buy side market making
                buy_prices = [9998, 9997, 9996, 9995]
                for i, price in enumerate(buy_prices[:self.MM_LEVELS_RR]):
                    if resin_position + (i+1) * self.MM_ORDER_SIZE_RR <= self.POSITION_LIMIT_RR:
                        resin_orders.append(Order("RAINFOREST_RESIN", price, self.MM_ORDER_SIZE_RR))
                
                # Sell side market making
                sell_prices = [10002, 10003, 10004, 10005]
                for i, price in enumerate(sell_prices[:self.MM_LEVELS_RR]):
                    if resin_position - (i+1) * self.MM_ORDER_SIZE_RR >= -self.POSITION_LIMIT_RR:
                        resin_orders.append(Order("RAINFOREST_RESIN", price, -self.MM_ORDER_SIZE_RR))
                
                # Improved scalping based on previous action
                if last_action_was_buy and resin_position > 8:
                        if bid_price >= current_mid + 1.5:  # Increased profit target
                            vol_to_sell = min(bid_volume, resin_position, 8)
                            if vol_to_sell > 0:
                                resin_orders.append(Order("RAINFOREST_RESIN", bid_price, -vol_to_sell))
                                resin_position -= vol_to_sell
                
                if last_action_was_sell and resin_position < -8:
                    for ask_price, ask_volume in order_depth.sell_orders.items():
                        if ask_price <= current_mid - 1.5:  # Increased profit target
                            vol_to_buy = min(-ask_volume, -resin_position, 8)
                            if vol_to_buy > 0:
                                resin_orders.append(Order("RAINFOREST_RESIN", ask_price, vol_to_buy))
                                resin_position += vol_to_buy
            
            result["RAINFOREST_RESIN"] = resin_orders
        
        # Process SQUID_INK strategy
        if "SQUID_INK" in state.order_depths:
            order_depth = state.order_depths["SQUID_INK"]
            current_position = positions.get("SQUID_INK", 0)
            ink_orders = []
            
            # Ensure all required keys are in squid_peak_data
            peak_data = trader_data['squid_ink']['squid_peak_data']
            required_keys = ['in_peak', 'in_short', 'entry_mode', 'exit_mode', 'peak_start_price', 
                            'peak_start_idx', 'highest_short_avg', 'exclude_until_idx', 'target_position']
            
            for key in required_keys:
                if key not in peak_data:
                    if key in ['in_peak', 'in_short', 'entry_mode', 'exit_mode']:
                        peak_data[key] = False
                    else:
                        peak_data[key] = 0
            
            if order_depth.sell_orders and order_depth.buy_orders:
                # Calculate current mid-price
                best_ask, ask_vol = list(order_depth.sell_orders.items())[0]
                best_bid, bid_vol = list(order_depth.buy_orders.items())[0]
                current_mid = (best_bid + best_ask) / 2.0
                
                # Update price history
                trader_data['squid_ink']['price_history'].append(current_mid)
                if len(trader_data['squid_ink']['price_history']) > 10000:  # Keep a reasonable history
                    trader_data['squid_ink']['price_history'] = trader_data['squid_ink']['price_history'][-10000:]
                
                # Handle entry mode - aggressively buying to target position
                if peak_data['entry_mode'] and current_position < peak_data['target_position']:
                    # Buy aggressively at best ask until we reach target position
                    remaining_to_buy = peak_data['target_position'] - current_position
                    buy_size = min(remaining_to_buy, -ask_vol)
                    if buy_size > 0:
                        ink_orders.append(Order("SQUID_INK", best_ask, buy_size))
                        current_position += buy_size
                        
                    # If we've reached target, exit entry mode
                    if current_position >= peak_data['target_position']:
                        peak_data['entry_mode'] = False
                
                # Handle exit mode - aggressively selling to target position
                elif peak_data['exit_mode'] and current_position > peak_data['target_position']:
                    # Sell aggressively at best bid until we reach target position
                    remaining_to_sell = current_position - peak_data['target_position']
                    sell_size = min(remaining_to_sell, bid_vol)
                    if sell_size > 0:
                        ink_orders.append(Order("SQUID_INK", best_bid, -sell_size))
                        current_position -= sell_size
                        
                    # If we've reached target and it's negative (short position), enter short mode
                    if current_position <= peak_data['target_position']:
                        peak_data['exit_mode'] = False
                        if peak_data['target_position'] < 0:
                            peak_data['in_short'] = True
                            peak_data['in_peak'] = False
                
                # Only proceed with strategy if not in entry/exit mode and we have enough data
                elif not peak_data['entry_mode'] and not peak_data['exit_mode'] and len(trader_data['squid_ink']['price_history']) >= self.INK_LONG_WINDOW:
                    all_prices = np.array(trader_data['squid_ink']['price_history'])
                    
                    # Create mask to exclude peak data but include data before peaks
                    valid_data = all_prices.copy()
                    if peak_data['in_peak'] or peak_data['in_short']:
                        # If we're in a peak or short position, use data up to peak start
                        if peak_data['peak_start_idx'] > 0:
                            valid_mask = np.ones(len(valid_data), dtype=bool)
                            valid_mask[peak_data['peak_start_idx']:] = False
                            valid_data = valid_data[valid_mask]
                    else:
                        # If we're not in a peak, use data after the last excluded index
                        valid_data = all_prices[peak_data['exclude_until_idx']:]
                    
                    # Only calculate if we have enough valid data
                    if len(valid_data) >= self.INK_LONG_WINDOW:
                        # Calculate long-term baseline (mean of previous 3000 prices)
                        long_avg = np.mean(valid_data[-self.INK_LONG_WINDOW:])
                        
                        # Calculate short-term average (mean of current 500 prices)
                        short_avg = np.mean(all_prices[-self.INK_SHORT_WINDOW:])
                        
                        # Track the highest short-term average during the peak
                        if peak_data['in_peak'] and short_avg > peak_data['highest_short_avg']:
                            peak_data['highest_short_avg'] = short_avg
                        
                        # BUY LOGIC: short-term average exceeds long-term baseline by threshold
                        if (short_avg > long_avg * (1 + self.INK_BUY_THRESHOLD)) and not peak_data['in_peak'] and not peak_data['in_short']:
                            # Enter aggressive buy mode to get to +50
                            peak_data['entry_mode'] = True
                            peak_data['target_position'] = self.INK_POSITION_SIZE
                            
                            # Also enter orders immediately this iteration
                            buy_size = min(self.INK_POSITION_SIZE - current_position, -ask_vol)
                            if buy_size > 0:
                                ink_orders.append(Order("SQUID_INK", best_ask, buy_size))
                                current_position += buy_size
                            
                            # Record that we've entered a peak
                            peak_data['in_peak'] = True
                            peak_data['peak_start_price'] = current_mid
                            peak_data['peak_start_idx'] = len(trader_data['squid_ink']['price_history']) - 1
                            peak_data['highest_short_avg'] = short_avg
                        
                        # SELL LOGIC: short-term average drops from peak by threshold
                        elif peak_data['in_peak'] and not peak_data['in_short']:
                            sell_threshold = peak_data['highest_short_avg'] * (1 - self.INK_SELL_DROP_PCT)
                            
                            if short_avg <= sell_threshold:
                                # Enter aggressive sell mode to get to -50
                                peak_data['exit_mode'] = True
                                peak_data['target_position'] = -self.INK_POSITION_SIZE
                                
                                # Also enter orders immediately this iteration
                                # First sell any existing long position
                                if current_position > 0:
                                    sell_size = min(current_position, bid_vol)
                                    if sell_size > 0:
                                        ink_orders.append(Order("SQUID_INK", best_bid, -sell_size))
                                        current_position -= sell_size
                                        bid_vol -= sell_size
                                
                                # Then enter short position
                                if current_position >= 0 and bid_vol > 0:
                                    short_size = min(self.INK_POSITION_SIZE + current_position, bid_vol)
                                    if short_size > 0:
                                        ink_orders.append(Order("SQUID_INK", best_bid, -short_size))
                                        current_position -= short_size
                        
                        # COVER SHORTS LOGIC: Price returns to pre-peak level
                        elif peak_data['in_short'] and current_position < 0:
                            if current_mid <= peak_data['peak_start_price']:
                                # Enter aggressive buy mode to get back to 0
                                peak_data['exit_mode'] = True
                                peak_data['target_position'] = 0
                                
                                # Also enter orders immediately this iteration
                                cover_size = min(-current_position, -ask_vol)
                                if cover_size > 0:
                                    ink_orders.append(Order("SQUID_INK", best_ask, cover_size))
                                    current_position += cover_size
                                
                                # If we've covered the position, reset tracking
                                if current_position >= 0:
                                    peak_data['in_short'] = False
                                    peak_data['exclude_until_idx'] = len(trader_data['squid_ink']['price_history']) - 1
            
            # Save updated peak tracking data
            trader_data['squid_ink']['squid_peak_data'] = peak_data
            result["SQUID_INK"] = ink_orders
        
        # ===== Process VOLCANIC_ROCK and options =====
        try:
            # Update market data and fit volatility model
            volatility_model = self.update_market_data(state)
            
            # Get underlying price
            underlying_product = "VOLCANIC_ROCK"
            underlying_price = None
            
            if underlying_product in state.order_depths:
                underlying_price = self.get_mid_price(state.order_depths[underlying_product])
                
                if underlying_price is not None and len(self.price_history[underlying_product]) >= self.min_data_points:
                    # 1. Generate rock trading signal
                    volatility_analysis = self.analyze_volatility_trends()
                    rock_signal = self.generate_trading_signal(volatility_analysis, underlying_price)
                    
                    # 2. Execute rock trading strategy
                    if rock_signal and rock_signal['action']:
                        rock_orders = self._execute_rock_strategy(state, underlying_price, volatility_model)
                        if rock_orders:
                            result[underlying_product] = rock_orders
                        
                        # 3. Execute aligned option trades using the same signal
                        option_opportunities = self.find_directional_option_trades(state, underlying_price, rock_signal)
                        
                        for product, opportunity in option_opportunities.items():
                            orders = self.generate_option_orders(product, opportunity)
                            
                            if orders:
                                result[product] = orders
        except Exception as e:
            # If there's an error, just continue with other strategies
            pass

        # Remove any products with empty order lists
        result = {k: v for k, v in result.items() if v}

        # Persist trader data
        trader_data_str = json.dumps(trader_data)

        return result, conversions, trader_data_str