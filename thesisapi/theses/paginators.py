from rest_framework import pagination


class ThesisPaginator(pagination.PageNumberPagination):
    page_size = 5


class BasePaginator(pagination.PageNumberPagination):
    page_size = 5
