from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from .models import Category, ServiceRequest, WorkOrder


class ServiceRequestModelTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.requester = user_model.objects.create_user(username="requester")
        self.technician = user_model.objects.create_user(username="technician")
        self.category = Category.objects.create(name="Electrical")

    def make_request(self, **overrides):
        values = {
            "requester": self.requester,
            "category": self.category,
            "title": "Faulty socket",
            "description": "Socket does not supply power.",
            "location": "Software Engineering Lab",
            "priority": 2,
        }
        values.update(overrides)
        return ServiceRequest.objects.create(**values)

    def build_request(self, **overrides):
        values = {
            "requester": self.requester,
            "category": self.category,
            "title": "Rule test",
            "description": "Testing the rule.",
            "location": "Lab",
            "priority": 2,
        }
        values.update(overrides)
        return ServiceRequest(**values)

    def test_default_status_is_open(self):
        item = self.make_request()
        self.assertEqual(item.status, ServiceRequest.Status.OPEN)

    def test_priority_validator_rejects_zero(self):
        item = self.build_request(priority=0)
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_database_constraint_rejects_priority_six(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_request(priority=6)

    def test_category_in_use_is_protected(self):
        self.make_request()
        with self.assertRaises(ProtectedError):
            self.category.delete()

    def test_request_accepts_only_one_work_order(self):
        item = self.make_request()
        WorkOrder.objects.create(service_request=item, technician=self.technician)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkOrder.objects.create(
                    service_request=item, technician=self.technician
                )

    def test_due_at_defaults_to_none(self):
        self.assertIsNone(self.make_request().due_at)

    def test_status_due_index_is_declared(self):
        names = [index.name for index in ServiceRequest._meta.indexes]
        self.assertIn("req_status_due_idx", names)

    def test_query_due_before_cutoff(self):
        now = timezone.now()
        soon = self.make_request(title="Soon", due_at=now + timedelta(hours=4))
        self.make_request(title="Later", due_at=now + timedelta(days=5))
        result = ServiceRequest.objects.filter(due_at__lt=now + timedelta(days=1))
        self.assertEqual(list(result), [soon])

    def test_is_overdue_only_for_active_requests(self):
        now = timezone.now()
        overdue = self.build_request(due_at=now - timedelta(hours=1))
        finished = self.build_request(
            status=ServiceRequest.Status.RESOLVED, due_at=now - timedelta(hours=1)
        )
        self.assertTrue(overdue.is_overdue)
        self.assertFalse(finished.is_overdue)

    def test_open_request_needs_no_resolution_data(self):
        self.build_request(status=ServiceRequest.Status.OPEN).full_clean()

    def test_resolved_without_resolved_at_fails(self):
        item = self.build_request(
            status=ServiceRequest.Status.RESOLVED, resolution_summary="Fixed."
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("resolved_at", ctx.exception.message_dict)

    def test_resolved_without_summary_fails(self):
        item = self.build_request(
            status=ServiceRequest.Status.RESOLVED, resolved_at=timezone.now()
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("resolution_summary", ctx.exception.message_dict)

    def test_closed_with_whitespace_summary_fails(self):
        item = self.build_request(
            status=ServiceRequest.Status.CLOSED,
            resolved_at=timezone.now(),
            resolution_summary="   ",
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("resolution_summary", ctx.exception.message_dict)

    def test_closed_missing_both_reports_both_fields(self):
        item = self.build_request(status=ServiceRequest.Status.CLOSED)
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertTrue(
            {"resolved_at", "resolution_summary"} <= set(ctx.exception.message_dict)
        )

    def test_resolved_with_time_and_summary_passes(self):
        self.build_request(
            status=ServiceRequest.Status.RESOLVED,
            resolved_at=timezone.now(),
            resolution_summary="Replaced the faulty socket.",
        ).full_clean()