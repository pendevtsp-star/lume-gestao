from django.db import migrations, models
import django.db.models.deletion


DEFAULT_CATEGORIES = {
    "rent": ("Aluguel", "fixed"),
    "payroll": ("Equipe", "fixed"),
    "supplies": ("Insumos", "variable"),
    "taxes": ("Impostos", "variable"),
    "systems": ("Sistemas", "fixed"),
    "other": ("Outros", "variable"),
}


def seed_expense_categories(apps, schema_editor):
    expense_category = apps.get_model("billing", "ExpenseCategory")
    expense = apps.get_model("billing", "Expense")
    existing_names = set(expense_category.objects.values_list("name", flat=True))
    expense_category.objects.bulk_create(
        [
            expense_category(name=name, kind=kind, active=True)
            for name, kind in DEFAULT_CATEGORIES.values()
            if name not in existing_names
        ]
    )
    categories = {
        code: expense_category.objects.get(name=name)
        for code, (name, kind) in DEFAULT_CATEGORIES.items()
    }

    fallback = categories["other"]
    for item in expense.objects.all():
        category = categories.get(item.legacy_category, fallback)
        expense.objects.filter(pk=item.pk).update(category=category, kind=category.kind)


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0002_expense_charge"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExpenseCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("name", models.CharField(max_length=120, unique=True, verbose_name="nome")),
                (
                    "kind",
                    models.CharField(
                        choices=[("fixed", "Fixa"), ("variable", "Variavel")],
                        default="variable",
                        max_length=20,
                        verbose_name="tipo padrao",
                    ),
                ),
                ("active", models.BooleanField(default=True, verbose_name="ativa")),
            ],
            options={
                "verbose_name": "categoria de despesa",
                "verbose_name_plural": "categorias de despesa",
                "ordering": ["name"],
            },
        ),
        migrations.RenameField(
            model_name="expense",
            old_name="category",
            new_name="legacy_category",
        ),
        migrations.AddField(
            model_name="expense",
            name="kind",
            field=models.CharField(
                choices=[("fixed", "Fixa"), ("variable", "Variavel")],
                default="variable",
                max_length=20,
                verbose_name="tipo",
            ),
        ),
        migrations.AddField(
            model_name="expense",
            name="category",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="expenses",
                to="billing.expensecategory",
                verbose_name="categoria",
            ),
        ),
        migrations.RunPython(seed_expense_categories, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="expense",
            name="legacy_category",
        ),
    ]
