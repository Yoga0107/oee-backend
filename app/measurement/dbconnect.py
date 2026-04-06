from sqlalchemy import create_engine, text
import numpy as np

class DBConnect:
    def __init__(self, db_url):
        self.engine = create_engine(db_url)
    
    def execute_query(self, query, params=None):
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params or {})
                return [dict(row._mapping) for row in result]
        except Exception as e:
            return f"Error Query: {e}"

    def execute_commit(self, query, params=None):
        try:
            with self.engine.begin() as conn:
                conn.execute(text(query), params or {})
            return "Success"
        except Exception as e:
            return f"Failed: {e}"

    def execute_to_numpy(self, query, params=None):
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params or {})
                
                data_raw = result.all()
                
                if not data_raw:
                    return np.array([])
                
                return np.array(data_raw)
                
        except Exception as e:
            return f"Error: {e}"


    

