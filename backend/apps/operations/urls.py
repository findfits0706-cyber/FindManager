from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    LocationViewSet,
    MyStaffCapabilityViewSet,
    StaffCapabilityViewSet,
    StaffLocationViewSet,
    WorkAreaViewSet,
    WorkCategoryViewSet,
    WorkTypeAvailabilityViewSet,
    WorkTypeViewSet,
)

router = DefaultRouter()
router.register("locations", LocationViewSet, basename="location")
router.register("work-areas", WorkAreaViewSet, basename="work-area")
router.register("work-categories", WorkCategoryViewSet, basename="work-category")
router.register("work-types", WorkTypeViewSet, basename="work-type")
router.register("work-type-availabilities", WorkTypeAvailabilityViewSet, basename="work-type-availability")
router.register("staff-locations", StaffLocationViewSet, basename="staff-location")
router.register("staff-capabilities", StaffCapabilityViewSet, basename="staff-capability")
router.register("my-capabilities", MyStaffCapabilityViewSet, basename="my-capability")

urlpatterns = [
    path("", include(router.urls)),
]
