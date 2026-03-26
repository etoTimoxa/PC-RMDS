import re
from typing import List, Dict


class EventGrouper:
    
    @staticmethod
    def get_event_key(event: Dict) -> str:
        message = event.get('message', '')
        cleaned_message = re.sub(r'record number \d+', '', message, flags=re.IGNORECASE)
        cleaned_message = re.sub(r'Record Number: \d+', '', cleaned_message, flags=re.IGNORECASE)
        cleaned_message = re.sub(r'Event ID: \d+', '', cleaned_message, flags=re.IGNORECASE)
        cleaned_message = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '', cleaned_message)
        
        return f"{event.get('log')}_{event.get('event_id')}_{event.get('source')}_{hash(cleaned_message)}"
    
    def group_events(self, events: List[Dict]) -> List[Dict]:
        grouped = {}
        
        for event in events:
            key = self.get_event_key(event)
            
            if key not in grouped:
                grouped[key] = {
                    'log': event.get('log'),
                    'event_id': event.get('event_id'),
                    'source': event.get('source'),
                    'severity': event.get('severity'),
                    'event_type': event.get('event_type'),
                    'message': event.get('message'),
                    'category': event.get('category'),
                    'user': event.get('user'),
                    'first_time': event.get('time'),
                    'last_time': event.get('time'),
                    'count': 1
                }
            else:
                grouped[key]['count'] += 1
                grouped[key]['last_time'] = event.get('time')
        
        # Преобразуем в список
        result = []
        for data in grouped.values():
            if data['count'] == 1:
                result.append({
                    'log': data['log'],
                    'event_id': data['event_id'],
                    'source': data['source'],
                    'severity': data['severity'],
                    'event_type': data['event_type'],
                    'time': data['first_time'],
                    'message': data['message'],
                    'category': data['category'],
                    'user': data['user'],
                    'is_grouped': False
                })
            else:
                result.append({
                    'log': data['log'],
                    'event_id': data['event_id'],
                    'source': data['source'],
                    'severity': data['severity'],
                    'event_type': data['event_type'],
                    'first_time': data['first_time'],
                    'last_time': data['last_time'],
                    'count': data['count'],
                    'message': data['message'],
                    'category': data['category'],
                    'user': data['user'],
                    'is_grouped': True
                })
        
        return result