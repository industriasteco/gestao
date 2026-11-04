from django.db import migrations

class Migration(migrations.Migration):
    dependencies=[('core','0001_initial')]
    operations=[migrations.RunSQL("""
    CREATE FUNCTION reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Auditoria imutável'; END; $$;
    CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON core_audit
    FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
    """, "DROP TRIGGER immutable_audit ON core_audit; DROP FUNCTION reject_audit_mutation();")]
