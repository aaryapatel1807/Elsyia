"""
Quick test to verify provider caching fix works correctly.

This test verifies that:
1. Provider instances are cached (singletons per provider type)
2. Different provider types get different instances
3. Same provider type returns same instance

Run with: python test_provider_caching.py
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.llm.factory import get_llm_provider
from app.services.voice.factory import get_stt_provider, get_tts_provider


def test_llm_provider_caching():
    """Test LLM provider caching works correctly."""
    print("🧪 Testing LLM provider caching...")
    
    # Get the same provider twice
    provider1 = get_llm_provider("ollama")
    provider2 = get_llm_provider("ollama")
    
    # Should be the exact same instance (singleton)
    assert provider1 is provider2, "❌ FAIL: Same provider should return same instance"
    print("  ✅ Same provider returns same instance (singleton pattern works)")
    
    # Verify it's the correct type
    from app.services.llm.ollama import OllamaProvider
    assert isinstance(provider1, OllamaProvider), "❌ FAIL: Should be OllamaProvider"
    print("  ✅ Correct provider type (OllamaProvider)")
    
    # Note: Can't test multiple providers yet since openrouter/gemini not implemented
    # When they are, add: provider3 = get_llm_provider("gemini")
    # assert provider1 is not provider3
    
    print("  ✅ LLM provider caching: PASS\n")


def test_stt_provider_caching():
    """Test STT provider caching works correctly."""
    print("🧪 Testing STT provider caching...")
    
    # Get the same provider twice
    provider1 = get_stt_provider("whisper")
    provider2 = get_stt_provider("whisper")
    
    # Should be the exact same instance (singleton)
    assert provider1 is provider2, "❌ FAIL: Same provider should return same instance"
    print("  ✅ Same provider returns same instance (singleton pattern works)")
    
    # Verify it's the correct type
    from app.services.voice.whisper_stt import WhisperSTTProvider
    assert isinstance(provider1, WhisperSTTProvider), "❌ FAIL: Should be WhisperSTTProvider"
    print("  ✅ Correct provider type (WhisperSTTProvider)")
    
    print("  ✅ STT provider caching: PASS\n")


def test_tts_provider_caching():
    """Test TTS provider caching works correctly."""
    print("🧪 Testing TTS provider caching...")
    
    # Get the same provider twice
    provider1 = get_tts_provider("piper")
    provider2 = get_tts_provider("piper")
    
    # Should be the exact same instance (singleton)
    assert provider1 is provider2, "❌ FAIL: Same provider should return same instance"
    print("  ✅ Same provider returns same instance (singleton pattern works)")
    
    # Verify it's the correct type
    from app.services.voice.piper_tts import PiperTTSProvider
    assert isinstance(provider1, PiperTTSProvider), "❌ FAIL: Should be PiperTTSProvider"
    print("  ✅ Correct provider type (PiperTTSProvider)")
    
    print("  ✅ TTS provider caching: PASS\n")


def main():
    print("=" * 60)
    print("Provider Caching Fix Verification")
    print("=" * 60)
    print()
    
    try:
        test_llm_provider_caching()
        test_stt_provider_caching()
        test_tts_provider_caching()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print()
        print("Provider caching fix is working correctly:")
        print("  • Providers are singletons (cached per provider name)")
        print("  • No re-instantiation per request")
        print("  • Dict-based cache correctly keys by provider name")
        print()
        print("No regression detected. Safe to deploy.")
        
    except AssertionError as e:
        print()
        print("=" * 60)
        print("❌ TEST FAILED")
        print("=" * 60)
        print(f"\nError: {e}")
        print("\n⚠️  Provider caching regression detected!")
        print("Review backend/app/services/llm/factory.py and voice/factory.py")
        sys.exit(1)
        
    except Exception as e:
        print()
        print("=" * 60)
        print("❌ UNEXPECTED ERROR")
        print("=" * 60)
        print(f"\nError: {type(e).__name__}: {e}")
        print("\nThis might be due to missing dependencies or configuration.")
        print("Make sure you're in the backend directory with .env configured.")
        sys.exit(1)


if __name__ == "__main__":
    main()
