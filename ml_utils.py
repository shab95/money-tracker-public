import pandas as pd
import pickle
import os
import db
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import FunctionTransformer
import numpy as np

def reshape_amount(x):
    """Helper to reshape amount series for sklearn."""
    if isinstance(x, np.ndarray):
        return x.reshape(-1, 1)
    return np.array(x).reshape(-1, 1)

MODEL_FILE = 'model.pkl'

class TransactionClassifier:
    def __init__(self):
        self.cat_model = None
        self.type_model = None
        self.vectorizer = None
        self.load_model()

    def load_model(self):
        """Loads the model from disk if it exists."""
        if os.path.exists(MODEL_FILE):
            try:
                with open(MODEL_FILE, 'rb') as f:
                    data = pickle.load(f)
                    self.cat_model = data.get('cat_model')
                    self.type_model = data.get('type_model')
                    # shared vectorizer if optimized, but pipeline handles it usually.
                    # Actually, if we use pipelines, the vectorizer is inside them.
                    
                    print("✅ ML Model loaded successfully.")
            except Exception as e:
                print(f"⚠️ Error loading model: {e}")
                self.cat_model = None
                self.type_model = None

    def train(self):
        """Fetches data from DB and retrains properties."""
        print("🧠 Training ML Models...")
        
        # 1. Fetch Data
        df = db.get_all_transactions()
        if df.empty:
            print("❌ No data to train on.")
            return "No data"

        # Filter out 'Uncategorized' for training Category model
        # For Type model, we can use everything that has a valid Type? 
        # Actually usually 'Uncategorized' stuff might have 'Expense' type default, which is fine.
        # But we want to learn from *Corrected* data.
        # So maybe filter for status='REVIEWED' or just assume current DB state is "truthy" enough excluding Uncategorized.
        
        # Train Category Model
        cat_df = df[df['category'] != 'Uncategorized']
        cat_df = cat_df[cat_df['category'].notna()]
        cat_df['description'] = cat_df['description'].fillna("") # Fix NoneType error
    
        if len(cat_df) > 10:
            # We use Description as main feature.
            # Maybe Amount too? (e.g. $1000 is likely Rent, $15 is likely Lunch)
            # For simplicity, let's start with Description + Amount.
            
            # Feature Engineering
            # We need a custom transformer for Amount to reshape it for sklearn
            
            # Pipeline
            # 1. Text -> TF-IDF
            # 2. Amount -> Passthrough
            # But combining them needs ColumnTransformer or FeatureUnion logic which handles DataFrames
            
            # Simple approach: Just text for now? 
            # Adding Amount significantly helps with things like "Spotify" (Subscription) vs "Spotify" (one off?) 
            # Actually Amount helps with "Check #123" -> Rent.
            
            # Let's use a simple Pipeline that takes just the description column if we pass Series.
            # But predict takes (desc, amount).
            
            # Let's try to do it properly with a ColumnTransformer.
            
            preprocessor = ColumnTransformer(
                transformers=[
                    ('text', TfidfVectorizer(stop_words='english', max_features=1000), 'description'),
                ]
            )
            
            # For Category, Text is 90% of signal.
            self.cat_model = Pipeline([
                ('tfidf', TfidfVectorizer(stop_words='english')),
                ('clf', RandomForestClassifier(n_estimators=100, random_state=42))
            ])
            
            self.cat_model.fit(cat_df['description'], cat_df['category'])
            print(f"✅ Category Model trained on {len(cat_df)} samples.")
        else:
            print("⚠️ Not enough categorized data to train Category model.")
            
        # Train Type Model (Income vs Expense vs Reimbursement)
        # This is where Amount (+/- from bank) matters. 
        # But our DB `amount` is always positive. The `type` tells the sign.
        # WE NEED THE RAW AMOUNT SIGN TO PREDICT TYPE.
        # The `raw_data` column might have it, but parsing it is slow.
        # Alternatively, we can assume:
        # If we are strictly predicting from "New Transaction", we have the raw amount.
        # But we need to train on something.
        # We can reconstruct "Signed Amount" from DB:
        # If Type=Expense -> -Amount
        # If Type=Income -> +Amount
        # If Type=Reimbursement -> +Amount (This is the tricky one! We want to distinguish Income vs Reimb)
        
        # Training Data Construction
        type_df = df.copy()
        
        def get_signed_amount(row):
            if row['type'] == 'Expense':
                return -1 * row['amount']
            else:
                return row['amount']
                
        type_df['signed_amount'] = type_df.apply(get_signed_amount, axis=1)
        
        # Features: Description + Signed Amount
        # We need a custom preprocessor that can handle a dict or dataframe logic?
        # Let's use ColumnTransformer on a DataFrame.
        
        type_features = type_df[['description', 'signed_amount']]
        type_features['description'] = type_features['description'].fillna("") # Fix NoneType error
        type_labels = type_df['type']
        
        if len(type_df) > 5:
            self.type_model = Pipeline([
                ('preprocessor', ColumnTransformer([
                    ('text', TfidfVectorizer(stop_words='english'), 'description'),
                    ('amt', FunctionTransformer(reshape_amount, validate=False), 'signed_amount')
                ])),
                ('clf', RandomForestClassifier(n_estimators=100, random_state=42))
            ])
            
            self.type_model.fit(type_features, type_labels)
            print(f"✅ Type Model trained on {len(type_df)} samples.")
            
        # Save
        with open(MODEL_FILE, 'wb') as f:
            pickle.dump({
                'cat_model': self.cat_model,
                'type_model': self.type_model
            }, f)
            
        return "Success"
        
    def predict(self, description, signed_amount):
        """
        Returns {category, type, confidence, cat_conf, type_conf}
        """
        result = {
            'category': 'Uncategorized',
            'type': 'Expense' if signed_amount < 0 else 'Income', # Default fallback
            'confidence': 0.0,
            'cat_confidence': 0.0,
            'type_confidence': 0.0
        }
        
        # 1. Predict Type
        if self.type_model:
            try:
                # Prepare DF for pipeline
                input_df = pd.DataFrame({'description': [description], 'signed_amount': [signed_amount]})
                pred_type = self.type_model.predict(input_df)[0]
                probs = self.type_model.predict_proba(input_df)
                confidence = np.max(probs)
                
                result['type'] = pred_type
                result['type_confidence'] = round(confidence, 2)
            except Exception as e:
                print(f"Type pred error: {e}")

        # 2. Predict Category
        if self.cat_model:
            try:
                pred_cat = self.cat_model.predict([description])[0]
                probs = self.cat_model.predict_proba([description])
                confidence = np.max(probs)
                
                result['category'] = pred_cat
                result['cat_confidence'] = round(confidence, 2)
            except Exception as e:
                print(f"Cat pred error: {e}")
                
        # Overall confidence could be min of both?
        result['confidence'] = min(result.get('cat_confidence', 0), result.get('type_confidence', 0))
        
        return result

# Singleton
classifier = TransactionClassifier()
