import data_input.models as m
print('MODELS:', [x for x in dir(m) if x[0].isupper()])
from data_input.models import SheetData, UploadRecord
print('SheetData:', SheetData.objects.count(), '| active:', SheetData.objects.filter(is_active=True).count())
print('UploadRecord:', UploadRecord.objects.count())
for r in UploadRecord.objects.all()[:8]:
    print('  rec', r.id, r.source, getattr(r, 'file_name', '?'), r.created_at)
