import os
import sys
from pyswip import Prolog

class AIEngine:
    def __init__(self, fastest_lap_telemetry=None):
        self.prolog = Prolog()
        self.rules_loaded = False
        
        # Path Handling
        current_dir = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
        rules_path = f"{current_dir}/rules.pl"
        
        if os.path.exists(rules_path):
            try:
                self.prolog.consult(rules_path)
                self.rules_loaded = True
            except: pass

    def update_telemetry(self, driver, snapshot):
        logs = []
        if not self.rules_loaded:
            return {"strategy": "OFFLINE", "tire_reason": "", "logs": []}
        
        # 1. Clean & Assert
        self.prolog.retractall("current_tire(_,_,_)")
        self.prolog.retractall("tire_temp(_,_)")
        self.prolog.retractall("gap_to_driver(_,_,_)")
        
        tyre = str(snapshot.get('tyre_compound', 'soft'))
        age = int(snapshot.get('tyre_age', 0))
        temp = int(snapshot.get('tyre_temp', 100))
        gap = float(snapshot.get('gap_to_leader', 0.0))
        
        # Assertions (Formatted for Frontend)
        self.prolog.assertz(f"current_tire('{driver}', {tyre}, {age})")
        logs.append(f"assert(tire('{driver}', {tyre}, {age})).")
        
        self.prolog.assertz(f"tire_temp('{driver}', {temp})")
        logs.append(f"assert(temp('{driver}', {temp})).")
        
        self.prolog.assertz(f"gap_to_driver('{driver}', 'LEADER', {gap})")
        
        # 2. Query Logic
        strategy = "MONITORING"
        try:
            q = list(self.prolog.query(f"get_engineer_message('{driver}', Msg)"))
            if q:
                strategy = q[0]['Msg']
                # Highlight Rule Match
                logs.append(f">> RULE MATCH: {strategy}")
        except: pass
            
        reason = ""
        try:
            q = list(self.prolog.query(f"get_tire_diagnosis('{driver}', S, R)"))
            if q:
                status = q[0]['S']
                reason = q[0]['R']
                if status != "OPTIMAL":
                    logs.append(f">> PHYSICS ALERT: {reason}")
        except: pass
            
        return {
            "strategy": strategy,
            "tire_reason": reason, # "OVERHEATING", "WEAR", etc.
            "logs": logs
        }