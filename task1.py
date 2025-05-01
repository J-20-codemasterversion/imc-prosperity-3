import json
import numpy as np
from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict

class Trader:
    # SQUID_INK strategy parameters
    INK_LONG_WINDOW = 3000      # Size of long-term baseline (previous 3000 prices)
    INK_SHORT_WINDOW = 500      # Size of short-term window (current 500 prices)
    INK_BUY_THRESHOLD = 0.01    # Buy when short-term avg > long-term avg by this percentage
    INK_SELL_DROP_PCT = 0.01    # Sell when short-term avg drops 5% from peak
    INK_POSITION_SIZE = 50      # Fixed position size for each trade

    # RAINFOREST_RESIN strategy parameters
    BUY_THRESHOLD_RR = 9995     # Buy threshold
    SELL_THRESHOLD_RR = 10005   # Sell threshold
    ORDER_SIZE_RR = 10           # Order size for HFT
    MM_LEVELS = 4               # Number of market making levels
    MM_ORDER_SIZE = 3           # Market making order size
    POSITION_LIMIT = 50         # Position limit for strategies

    def run(self, state: TradingState) -> tuple[Dict[str, List[Order]], int, str]:
        # Define helper functions inside run
        def calculate_ma(prices, period):
            """Calculate Simple Moving Average"""
            if len(prices) >= period:
                # Create a numpy array for faster calculation
                price_array = np.array(prices)
                # Use cumsum for efficient moving average calculation
                cumsum = np.cumsum(np.insert(price_array, 0, 0)) 
                return (cumsum[period:] - cumsum[:-period]) / period
            return [prices[-1]] if prices else [0]  # Not enough data
        
        def calculate_rsi(prices, period=14):
            """Calculate the RSI for a given price series"""
            # Need at least period+1 prices to calculate RSI
            if len(prices) <= period:
                return 50  # Default RSI value if not enough data
                
            # Convert to numpy array
            prices = np.array(prices)
            
            # Calculate price changes
            deltas = np.diff(prices)
            
            # Separate gains and losses
            gains = np.zeros_like(deltas)
            losses = np.zeros_like(deltas)
            gains[deltas > 0] = deltas[deltas > 0]
            losses[deltas < 0] = -deltas[deltas < 0]
            
            # Calculate average gains and losses
            avg_gain = np.zeros_like(deltas)
            avg_loss = np.zeros_like(deltas)
            
            # First average is simple average
            if len(gains) >= period:
                avg_gain[period-1] = np.mean(gains[:period])
                avg_loss[period-1] = np.mean(losses[:period])
                
                # Subsequent averages use the Wilder smoothing method
                for i in range(period, len(deltas)):
                    avg_gain[i] = (avg_gain[i-1] * (period-1) + gains[i]) / period
                    avg_loss[i] = (avg_loss[i-1] * (period-1) + losses[i]) / period
                
                # Calculate RS (Relative Strength) and RSI
                rs = avg_gain[period-1:] / (avg_loss[period-1:] + 1e-10)  # Add small value to avoid division by zero
                rsi = 100 - (100 / (1 + rs))
                
                return rsi[-1]  # Return the latest RSI value
            
            return 50  # Default RSI value if not enough data

        # Initialize result dictionary
        result = {}
        
        # Persistent state: price history for products
        price_history = {'RAINFOREST_RESIN': [], 'SQUID_INK': []}
        squid_indicators = {'short_ma': [], 'long_ma': [], 'rsi': 50, 'last_signal': 'none', 'last_price': 0}
        
        # Load previous state if available
        if state.traderData and state.traderData != "SAMPLE":
            try:
                data = json.loads(state.traderData)
                price_history = data.get('price_history', price_history)
                squid_indicators = data.get('squid_indicators', squid_indicators)
            except:
                price_history = {'RAINFOREST_RESIN': [], 'SQUID_INK': []}
                squid_indicators = {'short_ma': [], 'long_ma': [], 'rsi': 50, 'last_signal': 'none', 'last_price': 0}
        
        # Process each product
        for product in state.order_depths:
            order_depth = state.order_depths[product]
            
            if product == "RAINFOREST_RESIN":
                # RAINFOREST_RESIN strategy - enhanced with more aggressive market making
                resin_orders = []
                resin_position = state.position.get("RAINFOREST_RESIN", 0)
                
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
                    
                    price_history["RAINFOREST_RESIN"].append(current_mid)
                    if len(price_history["RAINFOREST_RESIN"]) > 100:
                        price_history["RAINFOREST_RESIN"] = price_history["RAINFOREST_RESIN"][-100:]
                
                    # Set dynamic thresholds based on recent history
                    if len(price_history["RAINFOREST_RESIN"]) >= 10:
                        recent_prices = np.array(price_history["RAINFOREST_RESIN"][-10:])
                        min_recent = np.min(recent_prices)
                        max_recent = np.max(recent_prices)
                        price_std = np.std(recent_prices)
                        
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
                    remaining_buy_capacity = self.POSITION_LIMIT - resin_position
                    if remaining_buy_capacity > 0:
                        for ask_price, ask_volume in order_depth.sell_orders.items():
                            if ask_price <= buy_threshold:
                                vol_to_buy = min(-ask_volume, remaining_buy_capacity, self.ORDER_SIZE_RR)
                                if vol_to_buy > 0:
                                    resin_orders.append(Order("RAINFOREST_RESIN", ask_price, vol_to_buy))
                                    resin_position += vol_to_buy
                                    remaining_buy_capacity -= vol_to_buy
                    
                    # Sell side processing
                    remaining_sell_capacity = self.POSITION_LIMIT + resin_position
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
                    for i, price in enumerate(buy_prices[:self.MM_LEVELS]):
                        if resin_position + (i+1) * self.MM_ORDER_SIZE <= self.POSITION_LIMIT:
                            resin_orders.append(Order("RAINFOREST_RESIN", price, self.MM_ORDER_SIZE))
                    
                    # Sell side market making
                    sell_prices = [10002, 10003, 10004, 10005]
                    for i, price in enumerate(sell_prices[:self.MM_LEVELS]):
                        if resin_position - (i+1) * self.MM_ORDER_SIZE >= -self.POSITION_LIMIT:
                            resin_orders.append(Order("RAINFOREST_RESIN", price, -self.MM_ORDER_SIZE))
                    
                    # Improved scalping based on previous action
                    if last_action_was_buy and resin_position > 8:
                        for bid_price, bid_volume in order_depth.buy_orders.items():
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
                
            elif product == "SQUID_INK":
                # SQUID_INK strategy - peak detection approach with aggressive entry/exit
                orders = []
                current_position = state.position.get("SQUID_INK", 0)
                
                # Initialize peak tracking data if not already present
                if 'squid_peak_data' not in squid_indicators:
                    squid_indicators['squid_peak_data'] = {
                        'in_peak': False,           # Whether we're currently in a peak
                        'in_short': False,          # Whether we're currently in a short position
                        'entry_mode': False,        # Whether we're currently trying to enter a position
                        'exit_mode': False,         # Whether we're currently trying to exit a position
                        'peak_start_price': 0,      # Price level at start of peak
                        'peak_start_idx': 0,        # Index at start of peak
                        'highest_short_avg': 0,     # Highest short-term avg during peak
                        'exclude_until_idx': 0,     # Index until which to exclude data
                        'target_position': 0        # Target position we're trying to reach
                    }
                
                peak_data = squid_indicators['squid_peak_data']
                
                if order_depth.sell_orders and order_depth.buy_orders:
                    # Calculate current mid-price
                    best_ask, ask_vol = list(order_depth.sell_orders.items())[0]
                    best_bid, bid_vol = list(order_depth.buy_orders.items())[0]
                    current_mid = (best_bid + best_ask) / 2.0
                    
                    # Update price history
                    price_history["SQUID_INK"].append(current_mid)
                    if len(price_history["SQUID_INK"]) > 10000:  # Keep a reasonable history
                        price_history["SQUID_INK"] = price_history["SQUID_INK"][-10000:]
                    
                    # Short at the start of each day (implementation doesn't actually know when days start)
                    # So we'll use the peak detection logic instead
                    
                    # Handle entry mode - aggressively buying to target position
                    if peak_data['entry_mode'] and current_position < peak_data['target_position']:
                        # Buy aggressively at best ask until we reach target position
                        remaining_to_buy = peak_data['target_position'] - current_position
                        buy_size = min(remaining_to_buy, -ask_vol)
                        if buy_size > 0:
                            orders.append(Order("SQUID_INK", best_ask, buy_size))
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
                            orders.append(Order("SQUID_INK", best_bid, -sell_size))
                            current_position -= sell_size
                            
                        # If we've reached target and it's negative (short position), enter short mode
                        if current_position <= peak_data['target_position']:
                            peak_data['exit_mode'] = False
                            if peak_data['target_position'] < 0:
                                peak_data['in_short'] = True
                                peak_data['in_peak'] = False
                    
                    # Only proceed with strategy if not in entry/exit mode and we have enough data
                    elif not peak_data['entry_mode'] and not peak_data['exit_mode'] and len(price_history["SQUID_INK"]) >= self.INK_LONG_WINDOW:
                        all_prices = np.array(price_history["SQUID_INK"])
                        
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
                                    orders.append(Order("SQUID_INK", best_ask, buy_size))
                                    current_position += buy_size
                                
                                # Record that we've entered a peak
                                peak_data['in_peak'] = True
                                peak_data['peak_start_price'] = current_mid
                                peak_data['peak_start_idx'] = len(price_history["SQUID_INK"]) - 1
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
                                            orders.append(Order("SQUID_INK", best_bid, -sell_size))
                                            current_position -= sell_size
                                            bid_vol -= sell_size
                                    
                                    # Then enter short position
                                    if current_position >= 0 and bid_vol > 0:
                                        short_size = min(self.INK_POSITION_SIZE + current_position, bid_vol)
                                        if short_size > 0:
                                            orders.append(Order("SQUID_INK", best_bid, -short_size))
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
                                        orders.append(Order("SQUID_INK", best_ask, cover_size))
                                        current_position += cover_size
                                    
                                    # If we've covered the position, reset tracking
                                    if current_position >= 0:
                                        peak_data['in_short'] = False
                                        peak_data['exclude_until_idx'] = len(price_history["SQUID_INK"]) - 1
                
                # Save updated peak tracking data
                squid_indicators['squid_peak_data'] = peak_data
                
                result["SQUID_INK"] = orders
        
        # Persist state for next iteration
        trader_data = json.dumps({
            'price_history': price_history,
            'squid_indicators': squid_indicators
        })
        
        return result, 0, trader_data