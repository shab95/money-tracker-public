import unittest
import sys
import os

# Add parent dir to path so we can import ml_utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ml_utils

class TestMLPredictions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure model is trained/loaded
        print("Ensuring model is loaded...")
        ml_utils.classifier.load_model()
        
    def test_uber_expense(self):
        # Known Valid Case
        pred = ml_utils.classifier.predict("Uber Trip", -15.50)
        print(f"\nUber Prediction: {pred}")
        # Note: We can't strictly assert Category because it depends on user's DB training data.
        # But Type should definitely be Expense.
        self.assertEqual(pred['type'], 'Expense')
        
    def test_capital_one_deposit(self):
        # User Requested Case
        # "deposit from capital one serv" -> Should be Income (Salary?) or Transfer?
        # Likely Income if positive.
        amount = 2000.00
        desc = "deposit from capital one serv"
        
        pred = ml_utils.classifier.predict(desc, amount)
        print(f"\n'{desc}' Prediction: {pred}")
        
        # We expect this to be Income or Transfer
        self.assertIn(pred['type'], ['Income', 'Transfer', 'Reimbursement'])
        
        # If the confidence is low, that's okay, but we want to see what it thinks.
        
    def test_reimbursement_logic(self):
        # Positive amount, but description implies expense refund?
        # This is tough for ML if it hasn't seen it. 
        # But let's check a generic one.
        pred = ml_utils.classifier.predict("Refund from Amazon", 25.00)
        print(f"\nRefund Prediction: {pred}")
        self.assertNotEqual(pred['type'], 'Expense')

if __name__ == '__main__':
    unittest.main()
