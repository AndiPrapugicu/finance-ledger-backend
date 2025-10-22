"""
Pagination utilities for D10-D12 server-side pagination
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from collections import OrderedDict


class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination class for all lists"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('page', self.page.number),
            ('page_size', self.page.paginator.per_page),
            ('total_pages', self.page.paginator.num_pages),
            ('results', data)
        ]))


class TransactionPagination(PageNumberPagination):
    """Custom pagination for transactions"""
    page_size = 15
    page_size_query_param = 'page_size'
    max_page_size = 50
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('page_info', {
                'current_page': self.page.number,
                'page_size': self.page.paginator.per_page,
                'total_pages': self.page.paginator.num_pages,
                'has_next': self.page.has_next(),
                'has_previous': self.page.has_previous()
            }),
            ('transactions', data)
        ]))


def paginate_transactions(transactions, page=1, page_size=15):
    """
    Manual pagination for in-memory transaction list
    Since TRANSACTIONS is a list, not a QuerySet
    """
    total_count = len(transactions)
    total_pages = (total_count + page_size - 1) // page_size  # Ceiling division
    
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    paginated_transactions = transactions[start_idx:end_idx]
    
    return {
        'count': total_count,
        'page_info': {
            'current_page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_previous': page > 1,
            'start_index': start_idx + 1 if paginated_transactions else 0,
            'end_index': min(end_idx, total_count)
        },
        'next': f'?page={page + 1}&page_size={page_size}' if page < total_pages else None,
        'previous': f'?page={page - 1}&page_size={page_size}' if page > 1 else None,
        'transactions': paginated_transactions
    }