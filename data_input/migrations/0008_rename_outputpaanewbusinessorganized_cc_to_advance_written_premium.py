from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        (
            "data_input",
            "0007_inputacquisitioncostornetsettlementrationewbusiness_and_more",
        ),
    ]

    operations = [
        migrations.RenameField(
            model_name="outputpaanewbusinessorganized",
            old_name="cc",
            new_name="advance_written_premium",
        ),
    ]
