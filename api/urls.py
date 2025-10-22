from django.urls import path, re_path
from . import views
from .accounts import (
    AccountListCreateView, 
    AccountDetailView, 
    account_hierarchy, 
    create_fixtures,
    create_cli_fixtures,
    list_cli_accounts
)
from .ledger_accounts_views import (
    ledger_accounts_list,
    ledger_accounts_grouped,
    ledger_account_detail
)
from .transactions import (
    create_transaction,
    reconcile_transaction,
    list_transactions,
    delete_transaction,
    create_double_entry_transaction,
    list_ledger_transactions,
    list_ledger_accounts
)
from .reports import (
    get_report,
    export_report,
    export_report_direct,
    test_export,
    simple_test,
    test_export_simple,
    test_export_markdown,
    list_reports
)
from .views import (
    import_csv,
    list_tags,
    dashboard_data,
    trial_balance,
    cashflow,
    unnecessary_spending,
    alerts
)
from .auth_views import (
    register_view,
    login_view,
    logout_view,
    profile_view,
    dashboard_data_view,
    user_reports_data_view,
    UserAccountListView,
    UserTransactionListView
)
from .wallet_views import (
    WalletDetailView,
    add_funds_view,
    transfer_funds_view,
    wallet_transactions_ledger_view,
    PaymentMethodListCreateView,
    PaymentMethodDetailView,
    WalletTransactionListView,
    wallet_summary_view,
    set_default_payment_method_view
)
from .user_profile_views import (
    user_financial_goals_view
)
from backend.services.reporting_service import ReportingService
from .budget_views import budget_list_create, create_default_budgets, delete_budget

urlpatterns = [
    # API Root
    path('', views.api_root, name='api-root'),
    
    # Authentication endpoints
    path('auth/register/', register_view, name='auth-register'),
    path('auth/login/', login_view, name='auth-login'),
    path('auth/logout/', logout_view, name='auth-logout'),
    path('auth/profile/', profile_view, name='auth-profile'),
    
    # User-specific endpoints
    path('user/dashboard/', dashboard_data_view, name='user-dashboard'),
    path('user/accounts/', UserAccountListView.as_view(), name='user-accounts'),
    path('user/transactions/', UserTransactionListView.as_view(), name='user-transactions'),
    path('user/reports/cashflow/', user_reports_data_view, name='user-reports'),
    path('user/financial-goals/', user_financial_goals_view, name='user-financial-goals'),
    
    # Wallet endpoints
    path('user/wallet/', WalletDetailView.as_view(), name='user-wallet'),
    path('user/wallet/add-funds/', add_funds_view, name='wallet-add-funds'),
    path('user/wallet/summary/', wallet_summary_view, name='wallet-summary'),
    path("user/wallet/transfer/", transfer_funds_view, name="wallet-transfer"),
    path('user/wallet/transactions/', WalletTransactionListView.as_view(), name='wallet-transactions'),
    path('user/wallet/transactions/ledger/', wallet_transactions_ledger_view, name='wallet-transactions-ledger'),
    path('user/payment-methods/', PaymentMethodListCreateView.as_view(), name='payment-methods'),
    path('user/payment-methods/<int:pk>/', PaymentMethodDetailView.as_view(), name='payment-method-detail'),
    path('user/payment-methods/<int:payment_method_id>/set-default/', set_default_payment_method_view, name='set-default-payment-method'),
    
    # Dashboard endpoint (legacy - will be replaced by user/dashboard/)
    path('dashboard/', dashboard_data, name='dashboard-data'),
    
    # Account endpoints
    path('accounts/', AccountListCreateView.as_view(), name='account-list-create'),
    path('accounts/<int:pk>/', AccountDetailView.as_view(), name='account-detail'),
    path('accounts/hierarchy/', account_hierarchy, name='account-hierarchy'),
    path('accounts/fixtures/', create_fixtures, name='create-fixtures'),
    path('accounts/cli-fixtures/', create_cli_fixtures, name='create-cli-fixtures'),
    path('accounts/cli-list/', list_cli_accounts, name='list-cli-accounts'),
    path('accounts/ledger/', list_ledger_accounts, name='list-ledger-accounts'),
    path('accounts/ledger/', list_ledger_accounts, name='ledger-accounts-list'),
    
    # Ledger Accounts endpoints (new - with real balances)
    path('ledger/accounts/', ledger_accounts_list, name='ledger-accounts-list-new'),
    path('ledger/accounts/grouped/', ledger_accounts_grouped, name='ledger-accounts-grouped'),
    path('ledger/accounts/<int:account_id>/', ledger_account_detail, name='ledger-account-detail'),
    
    # Transaction endpoints
    path('transactions/', create_transaction, name='transaction-create'),
    path('transactions/double-entry/', create_double_entry_transaction, name='transaction-double-entry-create'),
    path('transactions/list/', list_transactions, name='transaction-list'),
    path('transactions/ledger/', list_ledger_transactions, name='transaction-ledger-list'),
    path('transactions/<int:transaction_id>/', delete_transaction, name='transaction-delete'),
    path('transactions/<int:transaction_id>/reconcile/', reconcile_transaction, name='transaction-reconcile'),
    
    # Reports endpoints  
    path('reports/', list_reports, name='report-list'),
    path('reports/export/<str:format_type>/', export_report_direct, name='report-export-direct'),
    path('reports/<str:report_id>/export/', export_report, name='report-export'),
    path('reports/simple-test/', simple_test, name='simple-test'),
    path('reports/simple-export/', test_export_simple, name='simple-export'),
    path('reports/markdown-export/', test_export_markdown, name='markdown-export'),
    path('reports/test-download/', lambda request: export_report(request, 'test'), name='test-download'),
    path('reports/test/<path:report_id>/', test_export, name='test-export'),
    path('reports/trial-balance/', trial_balance, name='trial-balance'),
    path('reports/cashflow/', cashflow, name='cashflow'),
    path('reports/unnecessary/', unnecessary_spending, name='unnecessary-spending'),
    path('reports/<str:report_type>/', get_report, name='report-get'),  # Must be last!

    # Import endpoint
    path('import/', import_csv, name='import-csv'),

    #Tags
    path("tags/", list_tags, name="list-tags"),

    # Alerts endpoints
    path('alerts/', alerts, name='alerts'),

    # Budget endpoints
    path('budgets/', budget_list_create, name='budget-list-create'),
    path('budgets/create-defaults/', create_default_budgets, name='create-default-budgets'),
    path('budgets/<int:budget_id>/', delete_budget, name='budget-delete'),
]