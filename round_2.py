import json
import numpy as np
from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict

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
        "SQUID_INK": 100
    }
    
    # Basket compositions
    BASKET_COMPONENTS = {
        "PICNIC_BASKET1": {"CROISSANTS": 6, "JAMS": 3, "DJEMBES": 1},
        "PICNIC_BASKET2": {"CROISSANTS": 4, "JAMS": 2}
    }
    
    # Arbitrage parameters
    ARB_THRESHOLD_PCT = 0.0001      # Min 0.01% price difference to trigger arbitrage
    MAX_ARB_SIZE = 10              # Maximum size per arbitrage trade
    KELP_ORDERS_ENABLED = True     # Enable/disable KELP trading
    
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
    INK_SELL_DROP_PCT = 0.01    # Sell when short-term avg drops 5% from peak
    INK_POSITION_SIZE = 50      # Fixed position size for each trade

    # RAINFOREST_RESIN parameters
    BUY_THRESHOLD_RR = 9995     # Buy threshold
    SELL_THRESHOLD_RR = 10005   # Sell threshold
    ORDER_SIZE_RR = 10          # Order size for HFT
    MM_LEVELS_RR = 4            # Number of market making levels
    MM_ORDER_SIZE_RR = 3        # Market making order size
    POSITION_LIMIT_RR = 50      # Position limit for RESIN
    
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

        # Initialize result dictionary and conversions
        result = {}
        conversions = 0
        
        # Ensure position limits contains all products in order_depths
        for product in state.order_depths:
            if product not in self.POSITION_LIMITS:
                self.POSITION_LIMITS[product] = 60  # Default position limit
        
        # Initialize result for all products in order depths
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
                
                # Store fair value history
                if basket not in trader_data['fair_values']:
                    trader_data['fair_values'][basket] = []
                
                trader_data['fair_values'][basket].append(fair_values[basket])
                if len(trader_data['fair_values'][basket]) > 100:
                    trader_data['fair_values'][basket] = trader_data['fair_values'][basket][-100:]
                
                # Calculate basket spread (fair value - market price)
                if basket in mid_prices:
                    spread = fair_values[basket] - mid_prices[basket]
                    
                    # Store spread history
                    if basket not in trader_data['basket_spreads']:
                        trader_data['basket_spreads'][basket] = []
                    
                    trader_data['basket_spreads'][basket].append(spread)
                    if len(trader_data['basket_spreads'][basket]) > 100:
                        trader_data['basket_spreads'][basket] = trader_data['basket_spreads'][basket][-100:]
        
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
            
            # Calculate percentages for thresholds
            bid_pct_diff = basket_bid_vs_fair / fair_value if fair_value else 0
            ask_pct_diff = -basket_ask_vs_fair / fair_value if fair_value else 0
            
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
            
            # Case 1: Basket is OVERPRICED (sell basket, buy components)
            if bid_pct_diff > self.ARB_THRESHOLD_PCT:
                # Calculate arbitrage capacity
                arb_capacity = min(
                    max_basket_sell,
                    min([max_component_buy.get(comp, 0) for comp in self.BASKET_COMPONENTS[basket]]),
                    self.MAX_ARB_SIZE,
                    order_depth.buy_orders[best_basket_bid]
                )
                
                if arb_capacity > 0:
                    # Calculate if we can get all necessary components
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
                        
                        # Set conversion
                        if conversions == 0:
                            conversions = arb_capacity
            
            # Case 2: Basket is UNDERPRICED (buy basket, sell components)
            elif ask_pct_diff > self.ARB_THRESHOLD_PCT:
                # Calculate arbitrage capacity
                arb_capacity = min(
                    max_basket_buy,
                    min([max_component_sell.get(comp, 0) for comp in self.BASKET_COMPONENTS[basket]]),
                    self.MAX_ARB_SIZE,
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
                        
                        # Set conversion
                        if conversions == 0:
                            conversions = -arb_capacity
        
        # Process KELP with the base level strategy from kelp&resin_works.py
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
                    
                    # ======= AGGRESSIVE STRATEGY LOGIC =======
                    
                    # 1. PROFIT TAKING - Check if we should take profits on existing position
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
                    
                    # 2. Set dynamic thresholds based on current state
                    # Position bias: different thresholds based on current position
                    # Base shift bias: adjust thresholds during base shifts
                    
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
                    
                    # 3. AGGRESSIVE BUYING when price is below threshold
                    # Added momentum check to be more aggressive when momentum aligns
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
                    
                    # 4. AGGRESSIVE SELLING when price is above threshold
                    # Added momentum check to be more aggressive when momentum aligns
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
                    
                    # 5. If base is shifting, aggressively position in the direction of the shift
                    # This is in ADDITION to the opportunistic trades above
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
                    
                    # 6. Market making around current base level - only if not in a shift
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
                                
                    # 7. Always have at least one order in book to capture extreme moves
                    # These act as backstop orders
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
        
        # Process SQUID_INK strategy
        if "SQUID_INK" in state.order_depths:
            order_depth = state.order_depths["SQUID_INK"]
            current_position = positions.get("SQUID_INK", 0)
            ink_orders = []
            
            # Initialize squid_ink data if needed
            if 'squid_ink' not in trader_data:
                trader_data['squid_ink'] = {
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
                }
            
            # Make sure squid_peak_data is initialized properly
            if 'squid_peak_data' not in trader_data['squid_ink'] or not isinstance(trader_data['squid_ink']['squid_peak_data'], dict):
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
        
        # Remove any products with empty order lists
        result = {k: v for k, v in result.items() if v}
        
        # Persist trader data
        trader_data_str = json.dumps(trader_data)
        
        return result, conversions, trader_data_str