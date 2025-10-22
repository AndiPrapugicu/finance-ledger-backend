# Tests pentru Persoana C - D1-D3
# Frontend component unit tests pentru Account list + CLI integration test

import unittest
import subprocess
import json
import os

class CLIIntegrationTests(unittest.TestCase):
    """Integration tests for CLI tool - Persoana C task"""
    
    def setUp(self):
        """Setup test environment"""
        self.cli_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'cli')
        
    def test_ledger_init_command(self):
        """Test ledger init command"""
        result = subprocess.run(['node', 'ledger.js', 'init'], 
                              cwd=self.cli_path, 
                              capture_output=True, 
                              text=True)
        
        self.assertEqual(result.returncode, 0)
        self.assertIn('Fixtures created successfully', result.stdout)
        
    def test_ledger_acct_list_command(self):
        """Test ledger acct list command"""
        # First create fixtures
        subprocess.run(['node', 'ledger.js', 'init'], cwd=self.cli_path)
        
        # Then test list
        result = subprocess.run(['node', 'ledger.js', 'acct', 'list'], 
                              cwd=self.cli_path, 
                              capture_output=True, 
                              text=True)
        
        self.assertEqual(result.returncode, 0)
        self.assertIn('Asset', result.stdout)
        self.assertIn('Liability', result.stdout)

class APIEndpointsTests(unittest.TestCase):
    """Unit tests for API endpoints - Persoana C task"""
    
    def test_accounts_api_structure(self):
        """Test that API endpoints are properly structured"""
        # Import after Django setup
        from api.accounts import list_accounts, create_account
        
        # Test functions exist
        self.assertTrue(callable(list_accounts))
        self.assertTrue(callable(create_account))

if __name__ == '__main__':
    unittest.main()