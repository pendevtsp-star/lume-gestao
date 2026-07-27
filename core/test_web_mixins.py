from django.test import SimpleTestCase


class GenericViewMixinCompatibilityTests(SimpleTestCase):
    def test_core_views_keeps_backward_compatible_mixin_exports(self):
        from core.views import FormContextMixin as LegacyFormContextMixin
        from core.views import SearchableListView as LegacySearchableListView
        from core.web.mixins import FormContextMixin, SearchableListView

        self.assertIs(LegacyFormContextMixin, FormContextMixin)
        self.assertIs(LegacySearchableListView, SearchableListView)
