import win32evtlog
import win32evtlogutil
import win32security
from datetime import datetime, timedelta
from typing import List, Dict

from utils.constants import CRITICAL_EVENT_IDS 


class WindowsEventCollector:
    
    _last_record_numbers: Dict[str, int] = {}
    
    @staticmethod
    def get_severity(event_type: int, event_id: int = None) -> str:
        if event_type == win32evtlog.EVENTLOG_ERROR_TYPE:
            if event_id in CRITICAL_EVENT_IDS:
                return 'critical'
            return 'error'
        elif event_type == win32evtlog.EVENTLOG_WARNING_TYPE:
            return 'warning'
        elif event_type == win32evtlog.EVENTLOG_INFORMATION_TYPE:
            return 'info'
        elif event_type == win32evtlog.EVENTLOG_AUDIT_SUCCESS:
            return 'info'
        elif event_type == win32evtlog.EVENTLOG_AUDIT_FAILURE:
            return 'warning'
        return 'info'
    
    @classmethod
    def get_new_events(cls, logs: List[str] = None) -> List[Dict]:
        if logs is None:
            logs = ['System', 'Application']
        
        all_events = []
        
        for log_name in logs:
            try:
                hand = win32evtlog.OpenEventLog(None, log_name)
                num_records = win32evtlog.GetNumberOfEventLogRecords(hand)
                last_record = cls._last_record_numbers.get(log_name, 0)
                
                if num_records > last_record:
                    flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
                    records_to_read = num_records - last_record
                    events_data = win32evtlog.ReadEventLog(hand, flags, records_to_read)
                    
                    if events_data:
                        for event in reversed(events_data):
                            severity = cls.get_severity(event.EventType, event.EventID)
                            
                            message = ""
                            try:
                                message = win32evtlogutil.SafeFormatMessage(event, log_name)
                            except:
                                try:
                                    if event.StringInserts:
                                        message = ' '.join(event.StringInserts)
                                    else:
                                        message = f"Event ID: {event.EventID}, Source: {event.SourceName}"
                                except:
                                    message = f"Event ID: {event.EventID}"
                            
                            user_info = None
                            if event.Sid is not None:
                                try:
                                    domain, user, typ = win32security.LookupAccountSid(None, event.Sid)
                                    user_info = f"{domain}\\{user}"
                                except:
                                    user_info = str(event.Sid)
                            
                            all_events.append({
                                'log': log_name.lower(),
                                'event_id': event.EventID,
                                'source': event.SourceName,
                                'severity': severity,
                                'event_type': 'error' if severity in ['critical', 'error'] else severity,
                                'time': event.TimeGenerated.strftime('%Y-%m-%d %H:%M:%S'),
                                'message': message[:2000] if message else '',
                                'category': event.EventCategory,
                                'user': user_info,
                                'record_number': event.RecordNumber
                            })
                    
                    cls._last_record_numbers[log_name] = num_records
                
                win32evtlog.CloseEventLog(hand)
                
            except Exception as e:
                print(f"Ошибка чтения журнала {log_name}: {e}")
        
        return all_events
    
    @classmethod
    def get_all_events_last_24h(cls) -> List[Dict]:
        logs = ['System', 'Application']
        all_events = []
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        for log_name in logs:
            try:
                hand = win32evtlog.OpenEventLog(None, log_name)
                num_records = win32evtlog.GetNumberOfEventLogRecords(hand)
                cls._last_record_numbers[log_name] = num_records
                
                flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
                
                while True:
                    events_data = win32evtlog.ReadEventLog(hand, flags, 0)
                    if not events_data:
                        break
                    
                    for event in events_data:
                        event_time = event.TimeGenerated
                        if event_time < cutoff_time:
                            continue
                        
                        severity = cls.get_severity(event.EventType, event.EventID)
                        
                        message = ""
                        try:
                            message = win32evtlogutil.SafeFormatMessage(event, log_name)
                        except:
                            try:
                                if event.StringInserts:
                                    message = ' '.join(event.StringInserts)
                                else:
                                    message = f"Event ID: {event.EventID}, Source: {event.SourceName}"
                            except:
                                message = f"Event ID: {event.EventID}"
                        
                        user_info = None
                        if event.Sid is not None:
                            try:
                                domain, user, typ = win32security.LookupAccountSid(None, event.Sid)
                                user_info = f"{domain}\\{user}"
                            except:
                                user_info = str(event.Sid)
                        
                        all_events.append({
                            'log': log_name.lower(),
                            'event_id': event.EventID,
                            'source': event.SourceName,
                            'severity': severity,
                            'event_type': 'error' if severity in ['critical', 'error'] else severity,
                            'time': event_time.strftime('%Y-%m-%d %H:%M:%S'),
                            'message': message[:2000] if message else '',
                            'category': event.EventCategory,
                            'user': user_info,
                            'record_number': event.RecordNumber
                        })
                        
                        if len(all_events) > 5000:
                            break
                    
                    if len(all_events) > 5000:
                        break
                
                win32evtlog.CloseEventLog(hand)
                
            except Exception as e:
                print(f"Ошибка чтения журнала {log_name}: {e}")
        
        return all_events