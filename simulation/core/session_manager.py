import pytz
from datetime import datetime, time

class SessionManager:
    """
    Manages the strict 02:00 to 04:00 AM (Colombia Time) trading session.
    It dynamically handles the DST shift of the Broker's Server Time 
    (typically EET/EEST -> UTC+2/UTC+3) ensuring the Colombia window is statically anchored to UTC-5.
    """
    
    def __init__(self, 
                 start_hour: int = 2, 
                 start_minute: int = 0, 
                 end_hour: int = 4, 
                 end_minute: int = 0,
                 broker_tz: str = 'Europe/Bucharest', 
                 target_tz: str = 'America/Bogota'):
        
        self.start_hour = start_hour
        self.start_minute = start_minute
        self.end_hour = end_hour
        self.end_minute = end_minute
        
        # Using Bucharest as it perfectly maps the standard MT5 EET/EEST Forex Server times
        self.broker_timezone = pytz.timezone(broker_tz)
        self.target_timezone = pytz.timezone(target_tz)
        
    def is_in_session(self, broker_datetime: datetime) -> bool:
        """
        Receives an MT5 native timestamp (Broker Time) and returns True if it falls 
        within the target session window in the Target Timezone (Colombia Time).
        """
        # Ensure the datetime is localized to the broker's timezone
        if broker_datetime.tzinfo is None:
            # Localize assumes the provided time is exactly what's on the broker's clock
            localized_broker_time = self.broker_timezone.localize(broker_datetime)
        else:
            localized_broker_time = broker_datetime
            
        # Convert it safely to the target timezone (Colombia)
        colombia_time = localized_broker_time.astimezone(self.target_timezone)
        
        # Check against constraints
        current_time = colombia_time.time()
        start = time(self.start_hour, self.start_minute)
        end = time(self.end_hour, self.end_minute)
        
        return start <= current_time < end

if __name__ == "__main__":
    # --- TEST CASES FOR DST BIAS PREVENTION ---
    print("Testing Session Manager DST Resilience...\n")
    manager = SessionManager()
    
    # 1. European Winter (Standard Time - UTC+2 for Broker, UTC-5 for Colombia)
    # 2:00 AM Bogota = 7:00 AM UTC = 9:00 AM Broker Server (EET)
    # Let's test a broker timestamp of 9:00 AM on Jan 15th
    winter_timestamp = datetime(2024, 1, 15, 9, 30) # 9:30 AM Broker Time
    is_session = manager.is_in_session(winter_timestamp)
    print(f"Winter (Jan): Broker 09:30 -> Is in Session? {is_session} (Should be True, mapping to 02:30 Colombia)")

    winter_outside = datetime(2024, 1, 15, 10, 30) # 10:30 AM Broker Time
    is_outside = manager.is_in_session(winter_outside)
    print(f"Winter (Jan): Broker 10:30 -> Is in Session? {is_outside} (Should be False, mapping to 03:30? Actually 10:30 - 7hrs offset = 03:30, wait!)")
    # Actually wait: Broker is UTC+2, Bogota is UTC-5. Difference is 7 hours.
    # So 09:30 Broker - 7 hours = 02:30 Bogota (TRUE)
    # 10:30 Broker - 7 hours = 03:30 Bogota (TRUE)
    # 11:30 Broker - 7 hours = 04:30 Bogota (FALSE)
    
    print(f"Let's re-verify: 11:30 Broker time winter -> Is Session? {manager.is_in_session(datetime(2024, 1, 15, 11, 30))} (Should be False)")

    # 2. European Summer (DST Time - UTC+3 for Broker, UTC-5 for Colombia)
    # Difference is now 8 hours!
    # 2:00 AM Bogota = 7:00 AM UTC = 10:00 AM Broker Server (EEST)
    summer_timestamp = datetime(2024, 7, 15, 10, 30) # 10:30 Broker
    is_session_summer = manager.is_in_session(summer_timestamp)
    print(f"\nSummer (Jul): Broker 10:30 -> Is in Session? {is_session_summer} (Should be True, mapping to 02:30 Colombia)")
    
    summer_outside = datetime(2024, 7, 15, 12, 30) # 12:30 Broker -> 04:30 Colombia
    print(f"Summer (Jul): Broker 12:30 -> Is in Session? {manager.is_in_session(summer_outside)} (Should be False)")

    print("\nTests Complete.")
