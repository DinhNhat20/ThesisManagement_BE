from rest_framework import permissions
from rest_framework.permissions import BasePermission


class IsAuthenticated(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return False
        return request.user.is_authenticated


class IsMinistry(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role.code == 'ministry'


class IsLecturer(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return False
        return request.user.is_authenticated and request.user.role.code == 'lecturer'


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return False
        return request.user.is_authenticated and request.user.role.code == 'student'


class CommentOwner(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, comment):
        return super().has_permission(request, view) and request.user == comment.user


class PostOwner(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, post):
        return super().has_permission(request, view) and request.user == post.user


class ScoreOwner(permissions.IsAuthenticated):
    def has_object_permission(self, request, view, score):
        return super().has_permission(request, view) and request.user == score.council_detail.lecturer.user