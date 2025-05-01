
from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List, Dict
import math

class Trader:
    """
    Algorithmic trading strategy that combines:
    1. Volatility-based analysis for trading the underlying asset (VOLCANIC_ROCK)
    2. Time lag-based analysis for trading options
    """
    
    def __init__(self):
        # Initialize parameters and configuration
        self._initialize_configuration()
        self._initialize_state_variables()
        self._initialize_history_data()
        self._initialize_products()
    
    #======================================================================
    # Initialization Methods
    #======================================================================
    
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
    #======================================================================
    # Mathematical Utilities
    #======================================================================
    
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
    
    #======================================================================
    # Market Data Analysis
    #======================================================================
    
    def get_mid_price(self, order_depth):
        """Calculate mid price from order book."""
        if not order_depth.buy_orders and not order_depth.sell_orders:
            return None
            
        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders.keys())
            best_bid_volume = order_depth.buy_orders[best_bid]
        else:
            return min(order_depth.sell_orders.keys())
            
        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders.keys())
            best_ask_volume = abs(order_depth.sell_orders[best_ask])
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
        if len(self.returns_history[underlying_product]) > self.min_data_points and len(self.returns_history[product]) > self.min_data_points:
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
                
                print(f"Updated lag window for {product}: {self.lead_lag_windows[product]}")
    
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
    
    #======================================================================
    # VOLCANIC_ROCK Trading Strategy (Volatility-Based)
    #======================================================================
    
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
    
    #======================================================================
    # Options Trading Strategy (Time Lag-Based)
    #======================================================================
    
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
                
                if rock_orders:
                    print(f"Rock trading signal: {action} {size} units with strength {signal['signal_strength']:.2f}")
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
                
                action = opportunity['action']
                size = opportunity['size']
                diff_pct = opportunity['price_diff_pct'] * 100
                print(f"Option time-lag: {product} {action} {size} units with price diff {diff_pct:.2f}%")
        
        return option_orders
    
    def generate_option_orders(self, product, opportunity):
        """Generate orders for options based on time-lag prediction."""
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
    
    #======================================================================
    # Main Trading Logic
    #======================================================================
    
    def run(self, state: TradingState):
        """Main trading strategy with directional alignment for options."""
        # Initialize result dictionary
        result = {}
        
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
                                
                                action = opportunity['action']
                                size = opportunity['size']
                                print(f"Directional option: {product} {action} {size} units aligned with rock direction")
        
        except Exception as e:
            print(f"Error in run: {e}")
        
        # No conversions
        conversions = 0
        
        # Empty trader data string
        traderData = ""
        return result, conversions, traderData
    
    
    

