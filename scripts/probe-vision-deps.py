import importlib.util
print({name: bool(importlib.util.find_spec(name)) for name in ("PIL", "pytesseract", "cv2", "numpy")})
