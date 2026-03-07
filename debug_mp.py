import sys
print(f"Python: {sys.executable}")
try:
    import mediapipe as mp
    print(f"MediaPipe File: {mp.__file__}")
    print(f"Has solutions? {'solutions' in dir(mp)}")
    print(mp.solutions)
except Exception as e:
    print(f"Import Error: {e}")
