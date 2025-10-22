"""
E2E Tests for D7-D9: Reports + Export functionality
Test: request report → export CSV → parse & assert columns

Persoana C - D7-D9 E2E Tests
"""

import json
import csv
import io
from django.test import TestCase, Client
from api.temp_models import Account
from api.transactions import TRANSACTIONS, UNDO_STACK


class ReportsE2ETest(TestCase):
    """End-to-End tests for Reports functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        
        # Clear existing data
        TRANSACTIONS.clear()
        UNDO_STACK.clear()
        
        # Create test accounts
        self.checking = Account.objects.create(
            name="Test Checking",
            account_type="ASSET",
            parent=None
        )
        
        self.savings = Account.objects.create(
            name="Test Savings", 
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
        
        # Create test transactions
        self.create_test_transactions()
    
    def create_test_transactions(self):
        """Create sample transactions for testing"""
        test_transactions = [
            {
                'description': 'Salary Deposit',
                'date': '2024-01-15',
                'splits': [
                    {'account_id': self.checking.id, 'amount': 2500.00},
                    {'account_id': self.income.id, 'amount': -2500.00}
                ]
            },
            {
                'description': 'Grocery Shopping',
                'date': '2024-01-16', 
                'splits': [
                    {'account_id': self.checking.id, 'amount': -150.00},
                    {'account_id': self.expense.id, 'amount': 150.00}
                ]
            },
            {
                'description': 'Transfer to Savings',
                'date': '2024-01-17',
                'splits': [
                    {'account_id': self.checking.id, 'amount': -500.00},
                    {'account_id': self.savings.id, 'amount': 500.00}
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
    
    def test_cashflow_report_request_export_csv_e2e(self):
        """
        E2E Test: Request cashflow report → export CSV → parse & assert columns
        Core requirement for D7-D9
        """
        
        # Step 1: Request report
        report_response = self.client.get('/api/reports/cashflow/')
        
        self.assertEqual(report_response.status_code, 200)
        report_data = report_response.json()
        
        # Verify report structure
        self.assertIn('report_id', report_data)
        self.assertIn('report', report_data)
        
        report = report_data['report']
        self.assertEqual(report['report_type'], 'cashflow')
        self.assertIn('data', report)
        
        # Step 2: Export CSV
        report_id = report_data['report_id']
        export_response = self.client.get(f'/api/reports/{report_id}/export/?format=csv')
        
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response['Content-Type'], 'text/csv')
        self.assertIn('attachment', export_response['Content-Disposition'])
        
        # Step 3: Parse CSV and assert columns
        csv_content = export_response.content.decode('utf-8')
        csv_reader = csv.reader(io.StringIO(csv_content))
        
        # Parse CSV rows
        rows = list(csv_reader)
        
        # Assert CSV structure
        self.assertGreater(len(rows), 0, "CSV should have content")
        
        # Check header row
        header = rows[0]
        expected_columns = ['Type', 'Date', 'Account', 'Amount', 'Description']
        self.assertEqual(header, expected_columns, "CSV should have correct column headers")
        
        # Check data rows
        data_rows = [row for row in rows[1:] if row and row[0] in ['Inflow', 'Outflow']]
        self.assertGreater(len(data_rows), 0, "CSV should contain transaction data")
        
        # Verify data integrity
        inflow_rows = [row for row in data_rows if row[0] == 'Inflow']
        outflow_rows = [row for row in data_rows if row[0] == 'Outflow']
        
        self.assertGreater(len(inflow_rows), 0, "Should have inflow transactions")
        self.assertGreater(len(outflow_rows), 0, "Should have outflow transactions")
        
        # Verify specific transaction data
        salary_found = any('Salary Deposit' in row[4] for row in inflow_rows)
        grocery_found = any('Grocery Shopping' in row[4] for row in outflow_rows)
        
        self.assertTrue(salary_found, "Salary transaction should be in inflows")
        self.assertTrue(grocery_found, "Grocery transaction should be in outflows")
        
        # Verify amounts are properly formatted
        for row in data_rows:
            amount = row[3]
            self.assertTrue(amount.replace('.', '').replace(',', '').isdigit(), 
                          f"Amount should be numeric: {amount}")
        
        print(f"✅ E2E Test passed: Generated report {report_id}, exported CSV with {len(data_rows)} transactions")
    
    def test_balance_sheet_report_export_markdown_e2e(self):
        """
        E2E Test: Request balance sheet → export Markdown → verify format
        """
        
        # Step 1: Request balance sheet report
        report_response = self.client.get('/api/reports/balance_sheet/')
        
        self.assertEqual(report_response.status_code, 200)
        report_data = report_response.json()
        
        # Step 2: Export as Markdown
        report_id = report_data['report_id']
        export_response = self.client.get(f'/api/reports/{report_id}/export/?format=md')
        
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response['Content-Type'], 'text/markdown')
        
        # Step 3: Parse and verify Markdown content
        md_content = export_response.content.decode('utf-8')
        
        # Assert Markdown structure
        self.assertIn('# Balance Sheet Report', md_content)
        self.assertIn('## Balance Sheet', md_content)
        self.assertIn('## Totals', md_content)
        self.assertIn('Generated:', md_content)
        
        # Verify account types are present
        self.assertIn('### ASSET', md_content)
        
        # Verify table format
        self.assertIn('| Account | Balance |', md_content)
        self.assertIn('|---------|----------|', md_content)
        
        print(f"✅ Markdown export test passed for report {report_id}")
    
    def test_report_with_date_filters_e2e(self):
        """
        E2E Test: Request filtered report → verify filter application → export
        """
        
        # Step 1: Request report with date filter
        params = {
            'start_date': '2024-01-16',
            'end_date': '2024-01-17'
        }
        
        report_response = self.client.get('/api/reports/cashflow/', params)
        
        self.assertEqual(report_response.status_code, 200)
        report_data = report_response.json()
        
        # Verify filtering worked
        report = report_data['report']['data']
        
        # Should only include transactions from 01-16 to 01-17
        all_flows = report['inflows'] + report['outflows']
        
        for flow in all_flows:
            flow_date = flow['date']
            self.assertGreaterEqual(flow_date, '2024-01-16')
            self.assertLessEqual(flow_date, '2024-01-17')
        
        # Should exclude the salary from 01-15
        salary_flows = [f for f in all_flows if 'Salary' in f['description']]
        self.assertEqual(len(salary_flows), 0, "Salary from 01-15 should be filtered out")
        
        # Should include grocery from 01-16
        grocery_flows = [f for f in all_flows if 'Grocery' in f['description']]
        self.assertGreater(len(grocery_flows), 0, "Grocery from 01-16 should be included")
        
        print(f"✅ Date filter test passed, filtered to {len(all_flows)} transactions")
    
    def test_invalid_report_type_error_handling(self):
        """Test error handling for invalid report types"""
        
        response = self.client.get('/api/reports/invalid_type/')
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('available_types', data)
        self.assertIn('cashflow', data['available_types'])
        self.assertIn('balance_sheet', data['available_types'])
    
    def test_export_nonexistent_report_error_handling(self):
        """Test error handling for exporting non-existent reports"""
        
        response = self.client.get('/api/reports/nonexistent_id/export/?format=csv')
        
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('not found', data['error'].lower())
    
    def test_export_invalid_format_error_handling(self):
        """Test error handling for invalid export formats"""
        
        # Generate a report first
        report_response = self.client.get('/api/reports/cashflow/')
        report_id = report_response.json()['report_id']
        
        # Try invalid format
        response = self.client.get(f'/api/reports/{report_id}/export/?format=invalid')
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('supported_formats', data)
    
    def test_list_reports_endpoint(self):
        """Test the reports listing endpoint"""
        
        response = self.client.get('/api/reports/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertIn('available_types', data)
        self.assertIn('generated_reports', data)
        self.assertIn('report_count', data)
        
        # Check available report types
        available_types = data['available_types']
        self.assertIn('cashflow', available_types)
        self.assertIn('balance_sheet', available_types)