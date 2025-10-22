"""
Frontend integration tests for D10-D12
Tests for: filters + pagination functionality

Persoana C - D10-D12 Tests
"""

import json
import time
from django.test import TestCase, Client
from django.urls import reverse
from api.temp_models import Account
from api.transactions import TRANSACTIONS, UNDO_STACK


class FrontendIntegrationTest(TestCase):
    """Test frontend integration with filters and pagination"""
    
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
        
        self.income = Account.objects.create(
            name="Test Income",
            account_type="INCOME",
            parent=None
        )
        
        # Clear any existing data
        TRANSACTIONS.clear()
        UNDO_STACK.clear()
        
        # Create test transactions
        self.create_test_transactions()
    
    def create_test_transactions(self):
        """Create multiple test transactions for pagination testing"""
        test_transactions = [
            {
                'description': 'Grocery Store',
                'date': '2024-01-15',
                'splits': [
                    {'account_id': self.checking.id, 'amount': -50.00},
                    {'account_id': self.expense.id, 'amount': 50.00}
                ]
            },
            {
                'description': 'Salary Payment',
                'date': '2024-01-16',
                'splits': [
                    {'account_id': self.checking.id, 'amount': 2000.00},
                    {'account_id': self.income.id, 'amount': -2000.00}
                ]
            },
            {
                'description': 'Coffee Shop',
                'date': '2024-01-17',
                'splits': [
                    {'account_id': self.checking.id, 'amount': -5.50},
                    {'account_id': self.expense.id, 'amount': 5.50}
                ]
            },
            {
                'description': 'Freelance Work',
                'date': '2024-01-18',
                'splits': [
                    {'account_id': self.checking.id, 'amount': 500.00},
                    {'account_id': self.income.id, 'amount': -500.00}
                ]
            },
            {
                'description': 'Restaurant',
                'date': '2024-01-19',
                'splits': [
                    {'account_id': self.checking.id, 'amount': -25.75},
                    {'account_id': self.expense.id, 'amount': 25.75}
                ]
            }
        ]
        
        for tx_data in test_transactions:
            response = self.client.post(
                '/api/transactions/',
                data=json.dumps(tx_data),
                content_type='application/json'
            )
            self.assertEqual(response.status_code, 201)
    
    def test_accounts_pagination_basic(self):
        """Test basic account pagination functionality"""
        # Test default pagination
        response = self.client.get('/api/accounts/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Check pagination structure
        self.assertIn('count', data)
        self.assertIn('results', data)
        self.assertIn('next', data)
        self.assertIn('previous', data)
        self.assertIn('page', data)
        self.assertIn('page_size', data)
        self.assertIn('total_pages', data)
        
        # Should have our 3 test accounts
        self.assertEqual(data['count'], 3)
        self.assertEqual(len(data['results']), 3)
    
    def test_accounts_pagination_with_page_size(self):
        """Test account pagination with custom page size"""
        # Request smaller page size
        response = self.client.get('/api/accounts/?page_size=2')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data['count'], 3)
        self.assertEqual(len(data['results']), 2)  # Only 2 results per page
        self.assertEqual(data['page_size'], 2)
        self.assertEqual(data['total_pages'], 2)  # 3 accounts / 2 per page = 2 pages
        self.assertIsNotNone(data['next'])  # Should have next page
        
        # Test second page
        response2 = self.client.get('/api/accounts/?page=2&page_size=2')
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        
        self.assertEqual(len(data2['results']), 1)  # Last account
        self.assertIsNone(data2['next'])  # No next page
        self.assertIsNotNone(data2['previous'])  # Has previous page
    
    def test_transactions_pagination_basic(self):
        """Test basic transaction pagination"""
        response = self.client.get('/api/transactions/list/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Check pagination structure  
        self.assertIn('count', data)
        self.assertIn('transactions', data)
        self.assertIn('page_info', data)
        self.assertIn('next', data)
        self.assertIn('previous', data)
        
        # Should have our 5 test transactions
        self.assertEqual(data['count'], 5)
        self.assertEqual(len(data['transactions']), 5)
    
    def test_transactions_pagination_with_page_size(self):
        """Test transaction pagination with custom page size"""
        response = self.client.get('/api/transactions/list/?page_size=3')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data['count'], 5)
        self.assertEqual(len(data['transactions']), 3)
        self.assertEqual(data['page_info']['page_size'], 3)
        self.assertEqual(data['page_info']['total_pages'], 2)
        self.assertTrue(data['page_info']['has_next'])
        
        # Test second page
        response2 = self.client.get('/api/transactions/list/?page=2&page_size=3')
        data2 = response2.json()
        
        self.assertEqual(len(data2['transactions']), 2)  # Remaining 2 transactions
        self.assertFalse(data2['page_info']['has_next'])
        self.assertTrue(data2['page_info']['has_previous'])
    
    def test_transaction_filters_date_range(self):
        """Test transaction filtering by date range"""
        # Filter for transactions between Jan 16-18
        response = self.client.get(
            '/api/transactions/list/?start_date=2024-01-16&end_date=2024-01-18'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should have 3 transactions (Jan 16, 17, 18)
        self.assertEqual(data['count'], 3)
        
        # Check filter metadata
        filters = data['filters_applied']
        self.assertEqual(filters['start_date'], '2024-01-16')
        self.assertEqual(filters['end_date'], '2024-01-18')
        
        # Verify dates are within range
        for transaction in data['transactions']:
            tx_date = transaction['date']
            self.assertGreaterEqual(tx_date, '2024-01-16')
            self.assertLessEqual(tx_date, '2024-01-18')
    
    def test_transaction_filters_search(self):
        """Test transaction search filter"""
        # Search for transactions containing 'coffee'
        response = self.client.get('/api/transactions/list/?search=coffee')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should find 1 transaction
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['transactions'][0]['description'], 'Coffee Shop')
        self.assertEqual(data['filters_applied']['search'], 'coffee')
    
    def test_transaction_filters_reconciled_status(self):
        """Test transaction filtering by reconciled status"""
        # First, reconcile one transaction
        tx_id = None
        response = self.client.get('/api/transactions/list/')
        if response.json()['transactions']:
            tx_id = response.json()['transactions'][0]['transaction_id']
            
            # Reconcile it
            self.client.patch(f'/api/transactions/{tx_id}/reconcile/')
        
        # Test filter for reconciled transactions
        response = self.client.get('/api/transactions/list/?reconciled=true')
        data = response.json()
        
        self.assertEqual(data['count'], 1)
        self.assertTrue(data['transactions'][0]['is_reconciled'])
        
        # Test filter for unreconciled transactions  
        response2 = self.client.get('/api/transactions/list/?reconciled=false')
        data2 = response2.json()
        
        self.assertEqual(data2['count'], 4)  # Remaining unreconciled
        for transaction in data2['transactions']:
            self.assertFalse(transaction['is_reconciled'])
    
    def test_combined_filters_and_pagination(self):
        """Test combining filters with pagination"""
        # Filter + pagination together
        response = self.client.get(
            '/api/transactions/list/?search=shop&page_size=2&page=1'
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should find transactions with "shop" in description 
        # (Coffee Shop)
        self.assertGreater(data['count'], 0)
        self.assertEqual(data['page_info']['page_size'], 2)
        self.assertEqual(data['filters_applied']['search'], 'shop')
        
        for transaction in data['transactions']:
            self.assertIn('shop', transaction['description'].lower())
    
    def test_pagination_edge_cases(self):
        """Test pagination edge cases"""
        # Test invalid page number
        response = self.client.get('/api/transactions/list/?page=999')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should return empty results but valid structure
        self.assertEqual(len(data['transactions']), 0)
        
        # Test page size limits
        response2 = self.client.get('/api/transactions/list/?page_size=100')
        data2 = response2.json()
        
        # Should be limited to max page size (50)
        self.assertEqual(data2['page_info']['page_size'], 50)
    
    def test_filter_performance_with_large_dataset(self):
        """Test filter performance with larger dataset"""
        # Create additional transactions
        for i in range(20):
            tx_data = {
                'description': f'Test Transaction {i}',
                'date': f'2024-02-{(i % 28) + 1:02d}',
                'splits': [
                    {'account_id': self.checking.id, 'amount': -(i + 10)},
                    {'account_id': self.expense.id, 'amount': (i + 10)}
                ]
            }
            
            self.client.post(
                '/api/transactions/',
                data=json.dumps(tx_data),
                content_type='application/json'
            )
        
        # Now we should have 25 transactions total
        start_time = time.time()
        response = self.client.get('/api/transactions/list/?page_size=10&page=1')
        end_time = time.time()
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data['count'], 25)
        self.assertEqual(len(data['transactions']), 10)
        
        # Should be reasonably fast (< 1 second)
        self.assertLess(end_time - start_time, 1.0)
    
    def test_sort_order_consistency(self):
        """Test that pagination maintains consistent sort order"""
        # Get first page
        response1 = self.client.get('/api/transactions/list/?page_size=2&page=1')
        data1 = response1.json()
        
        # Get second page  
        response2 = self.client.get('/api/transactions/list/?page_size=2&page=2')
        data2 = response2.json()
        
        # Combine results
        all_transactions = data1['transactions'] + data2['transactions']
        
        # Should be sorted by date (newest first)
        dates = [tx['date'] for tx in all_transactions]
        self.assertEqual(dates, sorted(dates, reverse=True))
    
    def test_api_consistency_across_endpoints(self):
        """Test that pagination format is consistent across different endpoints"""
        # Test accounts pagination format
        accounts_response = self.client.get('/api/accounts/?page_size=5')
        accounts_data = accounts_response.json()
        
        # Test transactions pagination format
        transactions_response = self.client.get('/api/transactions/list/?page_size=5')
        transactions_data = transactions_response.json()
        
        # Both should have pagination metadata (though structure may differ)
        self.assertIn('count', accounts_data)
        self.assertIn('count', transactions_data)
        
        # Both should respect page_size parameter
        self.assertLessEqual(len(accounts_data['results']), 5)
        self.assertLessEqual(len(transactions_data['transactions']), 5)