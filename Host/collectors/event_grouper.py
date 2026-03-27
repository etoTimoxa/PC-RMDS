import re
import hashlib
from typing import List, Dict
from collections import defaultdict
from datetime import datetime


class EventGrouper:
    
    @staticmethod
    def get_event_key(event: Dict) -> str:
        log = event.get('log', '')
        event_id = event.get('event_id', 0)
        source = event.get('source', '')
        severity = event.get('severity', 'info')
        
        message = event.get('message', '')
        
        message = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z', '', message)
        message = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '', message)
        message = re.sub(r'\([0-9]+,[A-Z]+,[0-9]+\)', '', message)
        message = re.sub(r'\b\d{4,6}\b', '[ID]', message)
        message = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '[GUID]', message, flags=re.IGNORECASE)
        message = re.sub(r'[A-Za-z]:\\[^\\]+\\[^\\]+\.\w+', '[PATH]', message)
        message = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '[IP]', message)
        message = re.sub(r'S-1-5-\d+-\d+-\d+-\d+-\d+', '[SID]', message)
        message = re.sub(r'[A-Za-z0-9]+\\[A-Za-z0-9]+', '[USER]', message)
        message = re.sub(r'\d+\.\d+\.\d+\.\d+', '[VERSION]', message)
        message = re.sub(r'[0-9a-f]{32,}', '[HASH]', message, flags=re.IGNORECASE)
        message = re.sub(r'Название лицензии=[^\n]+', 'LicenseName=[LICENSE]', message)
        message = re.sub(r'Код лицензии=[0-9a-f-]+', 'LicenseId=[GUID]', message, flags=re.IGNORECASE)
        message = re.sub(r'record number \d+', '', message, flags=re.IGNORECASE)
        message = re.sub(r'\d+:\d+:\d+\.\d+', '[TIME]', message)
        message = re.sub(r'\b\d+\b', '[N]', message)
        message = ' '.join(message.split())
        
        message_hash = hashlib.md5(message.encode('utf-8')).hexdigest()[:16]
        
        return f"{log}_{event_id}_{source}_{severity}_{message_hash}"
    
    def group_events(self, events: List[Dict]) -> List[Dict]:
        grouped = defaultdict(lambda: {
            'log': None,
            'event_id': None,
            'source': None,
            'severity': None,
            'event_type': None,
            'original_message': None,
            'category': None,
            'user': None,
            'first_time': None,
            'last_time': None,
            'count': 0
        })
        
        for event in events:
            key = self.get_event_key(event)
            time_str = event.get('time', datetime.now().isoformat())
            
            if grouped[key]['count'] == 0:
                grouped[key]['log'] = event.get('log')
                grouped[key]['event_id'] = event.get('event_id')
                grouped[key]['source'] = event.get('source')
                grouped[key]['severity'] = event.get('severity')
                grouped[key]['event_type'] = event.get('event_type')
                grouped[key]['original_message'] = event.get('message')
                grouped[key]['category'] = event.get('category')
                grouped[key]['user'] = event.get('user')
                grouped[key]['first_time'] = time_str
            
            grouped[key]['last_time'] = time_str
            grouped[key]['count'] += 1
        
        result = []
        for key, data in grouped.items():
            if data['count'] == 1:
                result.append({
                    'log': data['log'],
                    'event_id': data['event_id'],
                    'source': data['source'],
                    'severity': data['severity'],
                    'event_type': data['event_type'],
                    'time': data['first_time'],
                    'message': data['original_message'],
                    'category': data['category'],
                    'user': data['user'],
                    'is_grouped': False
                })
            else:
                base_message = data['original_message']
                if len(base_message) > 150:
                    base_message = base_message[:150] + "..."
                
                grouped_message = f"{base_message} [повторяется {data['count']} раз, {data['first_time']} - {data['last_time']}]"
                
                result.append({
                    'log': data['log'],
                    'event_id': data['event_id'],
                    'source': data['source'],
                    'severity': data['severity'],
                    'event_type': data['event_type'],
                    'first_time': data['first_time'],
                    'last_time': data['last_time'],
                    'count': data['count'],
                    'message': grouped_message,
                    'category': data['category'],
                    'user': data['user'],
                    'is_grouped': True
                })
        
        result.sort(key=lambda x: x.get('first_time', x.get('time', '')), reverse=False)
        
        return result