"""
Integration tests for Transaction endpoints (D4-D6)
Tests for: reconcile toggle și undo command functionality

Persoana C - D4-D6 Tests
"""

import json
from django.test import TestCase, Client
from django.urls import reverse
from api.temp_models import Account


class TransactionIntegrationTest(TestCase):
    """Test transaction endpoints integration"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Create test accounts
        self.checking = Account.objects.create(
            name="Test Checking",
            account_type="ASSET",
            parent=None
        )
        
        self.expense = Account.objects.create(
            name="Test Expense", 
            account_type="EXPENSE",
            parent=None
        )
        
        # Clear any existing transactions
        from api.transactions import TRANSACTIONS, UNDO_STACK
        TRANSACTIONS.clear()
        UNDO_STACK.clear()
    
    def test_create_transaction_success(self):
        """Test successful transaction creation"""
        transaction_data = {
            'description': 'Test Transaction',
            'date': '2024-01-15',
            'splits': [
                {'account_id': self.checking.id, 'amount': -100.00},
                {'account_id': self.expense.id, 'amount': 100.00}
            ]
        }
        
        response = self.client.post(
            '/api/transactions/',
            data=json.dumps(transaction_data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn('transaction_id', data)
        self.assertIn('message', data)
        self.assertEqual(len(data['entries']), 2)
        
        # Verify transaction is stored
        response = self.client.get('/api/transactions/list/')
        self.assertEqual(response.status_code, 200)
        transactions = response.json()['transactions']
        self.assertEqual(len(transactions), 1)
    
    def test_create_transaction_unbalanced_fails(self):
        """Test transaction creation fails when splits don't balance"""
        transaction_data = {
            'description': 'Unbalanced Transaction',
            'date': '2024-01-15',
            'splits': [
                {'account_id': self.checking.id, 'amount': -100.00},
                {'account_id': self.expense.id, 'amount': 150.00}  # Doesn't balance!
            ]
        }
        
        response = self.client.post(
            '/api/transactions/',
            data=json.dumps(transaction_data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('balance', data['error'].lower())
    
    def test_reconcile_toggle_flow(self):
        """Test reconcile toggle functionality (core requirement)"""
        # Create a transaction first
        transaction_data = {
            'description': 'Reconcile Test Transaction',
            'date': '2024-01-15',
            'splits': [
                {'account_id': self.checking.id, 'amount': -50.00},
                {'account_id': self.expense.id, 'amount': 50.00}
            ]
        }
        
        create_response = self.client.post(
            '/api/transactions/',
            data=json.dumps(transaction_data),
            content_type='application/json'
        )
        
        self.assertEqual(create_response.status_code, 201)
        transaction_id = create_response.json()['transaction_id']
        
        # Test reconcile (should set to True)
        reconcile_response = self.client.patch(
            f'/api/transactions/{transaction_id}/reconcile/'
        )
        
        self.assertEqual(reconcile_response.status_code, 200)
        reconcile_data = reconcile_response.json()
        self.assertTrue(reconcile_data['is_reconciled'])
        self.assertEqual(reconcile_data['transaction_id'], transaction_id)
        self.assertIn('reconciled', reconcile_data['message'].lower())
        
        # Test toggle back (should set to False)
        unreconcile_response = self.client.patch(
            f'/api/transactions/{transaction_id}/reconcile/'
        )
        
        self.assertEqual(unreconcile_response.status_code, 200)
        unreconcile_data = unreconcile_response.json()
        self.assertFalse(unreconcile_data['is_reconciled'])
        self.assertIn('unreconciled', unreconcile_data['message'].lower())
        
        # Verify all entries are updated
        self.assertEqual(len(unreconcile_data['updated_entries']), 2)
        for entry in unreconcile_data['updated_entries']:
            self.assertFalse(entry['is_reconciled'])
    
    def test_reconcile_nonexistent_transaction(self):
        """Test reconcile with non-existent transaction ID"""
        response = self.client.patch('/api/transactions/nonexistent-id/reconcile/')
        
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('not found', data['error'].lower())
    
    def test_undo_create_transaction_flow(self):
        """Test undo command for transaction creation (core requirement)"""
        # Create a transaction
        transaction_data = {
            'description': 'Transaction to Undo',
            'date': '2024-01-15',
            'splits': [
                {'account_id': self.checking.id, 'amount': -75.00},
                {'account_id': self.expense.id, 'amount': 75.00}
            ]
        }
        
        create_response = self.client.post(
            '/api/transactions/',
            data=json.dumps(transaction_data),
            content_type='application/json'
        )
        
        self.assertEqual(create_response.status_code, 201)
        transaction_id = create_response.json()['transaction_id']
        
        # Verify transaction exists
        list_response = self.client.get('/api/transactions/list/')
        self.assertEqual(len(list_response.json()['transactions']), 1)
        
        # Undo the transaction creation
        undo_response = self.client.post('/api/transactions/undo/')
        
        self.assertEqual(undo_response.status_code, 200)
        undo_data = undo_response.json()
        self.assertIn('message', undo_data)
        self.assertEqual(undo_data['action'], 'CREATE_TRANSACTION_UNDONE')
        self.assertEqual(undo_data['transaction_id'], transaction_id)
        
        # Verify transaction is removed
        list_response = self.client.get('/api/transactions/list/')
        self.assertEqual(len(list_response.json()['transactions']), 0)
    
    def test_undo_reconcile_flow(self):
        """Test undo command for reconcile operation (core requirement)"""
        # Create and reconcile a transaction
        transaction_data = {
            'description': 'Reconcile Undo Test',
            'date': '2024-01-15',
            'splits': [
                {'account_id': self.checking.id, 'amount': -25.00},
                {'account_id': self.expense.id, 'amount': 25.00}
            ]
        }
        
        create_response = self.client.post(
            '/api/transactions/',
            data=json.dumps(transaction_data),
            content_type='application/json'
        )
        transaction_id = create_response.json()['transaction_id']
        
        # Reconcile the transaction
        reconcile_response = self.client.patch(
            f'/api/transactions/{transaction_id}/reconcile/'
        )
        self.assertTrue(reconcile_response.json()['is_reconciled'])
        
        # Undo the reconcile operation
        undo_response = self.client.post('/api/transactions/undo/')
        
        self.assertEqual(undo_response.status_code, 200)
        undo_data = undo_response.json()
        self.assertEqual(undo_data['action'], 'RECONCILE_UNDONE')
        self.assertEqual(undo_data['transaction_id'], transaction_id)
        self.assertFalse(undo_data['reverted_to_reconciled'])
        
        # Verify transaction is back to unreconciled
        self.assertEqual(len(undo_data['updated_entries']), 2)
        for entry in undo_data['updated_entries']:
            self.assertFalse(entry['is_reconciled'])
    
    def test_undo_empty_stack(self):
        """Test undo when nothing to undo"""
        # Clear undo stack
        from api.transactions import UNDO_STACK
        UNDO_STACK.clear()
        
        response = self.client.post('/api/transactions/undo/')
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('no actions', data['error'].lower())
    
    def test_full_integration_workflow(self):
        """Test complete workflow: create -> reconcile -> undo reconcile -> undo create"""
        # Step 1: Create transaction
        transaction_data = {
            'description': 'Full Workflow Test',
            'date': '2024-01-15',
            'splits': [
                {'account_id': self.checking.id, 'amount': -200.00},
                {'account_id': self.expense.id, 'amount': 200.00}
            ]
        }
        
        create_response = self.client.post(
            '/api/transactions/',
            data=json.dumps(transaction_data),
            content_type='application/json'
        )
        transaction_id = create_response.json()['transaction_id']
        
        # Step 2: Reconcile transaction
        reconcile_response = self.client.patch(
            f'/api/transactions/{transaction_id}/reconcile/'
        )
        self.assertTrue(reconcile_response.json()['is_reconciled'])
        
        # Step 3: Undo reconcile
        undo_reconcile_response = self.client.post('/api/transactions/undo/')
        self.assertEqual(undo_reconcile_response.json()['action'], 'RECONCILE_UNDONE')
        
        # Step 4: Undo transaction creation
        undo_create_response = self.client.post('/api/transactions/undo/')
        self.assertEqual(undo_create_response.json()['action'], 'CREATE_TRANSACTION_UNDONE')
        
        # Step 5: Verify everything is clean
        list_response = self.client.get('/api/transactions/list/')
        self.assertEqual(len(list_response.json()['transactions']), 0)
        self.assertEqual(list_response.json()['undo_stack_size'], 0)
    
    def test_complex_transaction_with_multiple_splits(self):
        """Test transaction with more than 2 splits"""
        # Create additional account
        income = Account.objects.create(
            name="Test Income",
            account_type="INCOME", 
            parent=None
        )
        
        transaction_data = {
            'description': 'Complex Multi-Split Transaction',
            'date': '2024-01-15',
            'splits': [
                {'account_id': self.checking.id, 'amount': 1000.00},
                {'account_id': self.expense.id, 'amount': -300.00},
                {'account_id': income.id, 'amount': -700.00}
            ]
        }
        
        response = self.client.post(
            '/api/transactions/',
            data=json.dumps(transaction_data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data['entries']), 3)
        
        # Test reconcile works with multiple splits
        transaction_id = data['transaction_id']
        reconcile_response = self.client.patch(
            f'/api/transactions/{transaction_id}/reconcile/'
        )
        
        self.assertEqual(reconcile_response.status_code, 200)
        self.assertEqual(len(reconcile_response.json()['updated_entries']), 3)