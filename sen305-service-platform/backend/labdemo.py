from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils import timezone

from requests_app.models import Category, ServiceRequest

User = get_user_model()
requester, _ = User.objects.get_or_create(username="requester1")
electrical, _ = Category.objects.get_or_create(
    name="Electrical",
    defaults={"description": "Electrical faults and maintenance"},
)
ict, _ = Category.objects.get_or_create(
    name="ICT Support",
    defaults={"description": "Computers, networks and software"},
)
now = timezone.now()

print("===== TASK 1: two requests, query due before a chosen time =====")
ServiceRequest.objects.filter(title__startswith="SLA test").delete()
ServiceRequest.objects.create(
    requester=requester, category=electrical, title="SLA test - due soon",
    description="Synthetic request due early.", location="Lab 2",
    priority=2, due_at=now + timedelta(hours=4),
)
ServiceRequest.objects.create(
    requester=requester, category=electrical, title="SLA test - due later",
    description="Synthetic request due later.", location="Lab 2",
    priority=3, due_at=now + timedelta(days=5),
)
cutoff = now + timedelta(days=1)
due_qs = ServiceRequest.objects.filter(
    status__in=ServiceRequest.ACTIVE_STATUSES, due_at__lt=cutoff
).filter(title__startswith="SLA test")
print("cutoff:", cutoff)
print("due before cutoff:", [r.title for r in due_qs])
print("SQL:", due_qs.query)

print()
print("===== TASK 2: resolution rule with full_clean() =====")


def build(**kw):
    values = dict(
        requester=requester, category=electrical, title="Rule test",
        description="Testing the rule.", location="Lab", priority=2,
    )
    values.update(kw)
    return ServiceRequest(**values)


try:
    build(status="resolved").full_clean()
except ValidationError as e:
    print("resolved with nothing ->", e.message_dict)

try:
    build(status="closed", resolved_at=now, resolution_summary="   ").full_clean()
except ValidationError as e:
    print("closed, blank summary ->", e.message_dict)

build(status="resolved", resolved_at=now, resolution_summary="Replaced socket.").full_clean()
print("resolved with both -> passes")
build(status="open").full_clean()
print("open with neither -> passes")

print()
print("===== TASK 3: 12 synthetic requests and query analysis =====")
ServiceRequest.objects.filter(title__startswith="Synthetic").delete()
statuses = ["open", "assigned", "resolved"]
for i in range(12):
    status = statuses[i % 3]
    extra = {}
    if status == "resolved":
        extra = {"resolved_at": now, "resolution_summary": "Synthetic fix."}
    item = ServiceRequest.objects.create(
        requester=requester,
        category=electrical if i % 2 == 0 else ict,
        title="Synthetic request %02d" % i,
        description="Synthetic laboratory data.",
        location="Lab",
        priority=(i % 5) + 1,
        status=status,
        due_at=now + timedelta(hours=i * 6 - 24),
        **extra,
    )
    ServiceRequest.objects.filter(pk=item.pk).update(
        created_at=now - timedelta(days=12 - i)
    )

print(list(
    ServiceRequest.objects.filter(title__startswith="Synthetic")
    .values_list("category__name", "status").annotate(n=Count("id"))
    .order_by("category__name", "status")
))

qs = (
    ServiceRequest.objects
    .filter(category=electrical, status__in=["open", "assigned"])
    .order_by("priority", "created_at")
)
print()
print("QUERY SQL:")
print(qs.query)
print()
print("EXPLAIN:")
print(qs.explain())
print()
for r in qs:
    print(r.priority, r.created_at.date(), r.status, r.title)