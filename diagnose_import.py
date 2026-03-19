with open('diagnose_log.txt', 'w') as f:
    f.write("Attempting to import app...\n")
    try:
        from app import app
        f.write("Import successful!\n")
    except Exception as e:
        import traceback
        f.write("Import failed!\n")
        f.write(traceback.format_exc())
