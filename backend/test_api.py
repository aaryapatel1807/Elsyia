"""
Quick API Test Script

Test the Elysia backend without needing curl or Postman.
Run this after starting the server to verify everything works.

Usage:
    python test_api.py
"""

import asyncio
import json
from typing import Optional

import httpx


BASE_URL = "http://localhost:8000"


async def test_health():
    """Test health endpoint."""
    print("\n🔍 Testing health endpoint...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200


async def test_status():
    """Test status endpoint."""
    print("\n🔍 Testing status endpoint...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/v1/status")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200


async def test_providers():
    """Test providers endpoint."""
    print("\n🔍 Testing providers endpoint...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/v1/status/providers")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200


async def test_chat_non_streaming():
    """Test chat endpoint (non-streaming)."""
    print("\n🔍 Testing chat (non-streaming)...")
    async with httpx.AsyncClient(timeout=60.0) as client:
        payload = {
            "message": "Hello! Please introduce yourself in one sentence.",
            "stream": False
        }
        response = await client.post(
            f"{BASE_URL}/api/v1/chat",
            json=payload
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {data['response'][:200]}...")
            print(f"Conversation ID: {data['conversation_id']}")
            return True, data['conversation_id']
        else:
            print(f"Error: {response.text}")
            return False, None


async def test_chat_streaming():
    """Test chat endpoint (streaming)."""
    print("\n🔍 Testing chat (streaming)...")
    async with httpx.AsyncClient(timeout=60.0) as client:
        payload = {
            "message": "Count from 1 to 5, one number per line.",
            "stream": True
        }
        
        print("Response: ", end="", flush=True)
        async with client.stream(
            "POST",
            f"{BASE_URL}/api/v1/chat",
            json=payload
        ) as response:
            if response.status_code != 200:
                print(f"\nError: {response.status_code}")
                return False
            
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data["type"] == "token":
                        print(data["content"], end="", flush=True)
                    elif data["type"] == "done":
                        print(f"\n✓ Done (conversation: {data['conversation_id']})")
                        return True
        
        return False


async def test_conversation_history(conversation_id: Optional[str]):
    """Test conversation history endpoint."""
    if not conversation_id:
        print("\n⚠️  Skipping history test (no conversation ID)")
        return False
    
    print(f"\n🔍 Testing conversation history...")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/chat/history/{conversation_id}"
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Messages: {len(data['messages'])}")
            for msg in data['messages']:
                print(f"  {msg['role']}: {msg['content'][:50]}...")
            return True
        else:
            print(f"Error: {response.text}")
            return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("🧪 Elysia Backend API Tests")
    print("=" * 60)
    print("\nMake sure the server is running:")
    print("  cd backend && uv run python -m app.main")
    print("\nMake sure Ollama is running:")
    print("  ollama serve")
    print("\nPress Enter to start tests...")
    input()
    
    results = []
    
    # Basic tests
    results.append(("Health Check", await test_health()))
    results.append(("Status", await test_status()))
    results.append(("Providers", await test_providers()))
    
    # Chat tests
    success, conv_id = await test_chat_non_streaming()
    results.append(("Chat (non-streaming)", success))
    
    results.append(("Chat (streaming)", await test_chat_streaming()))
    
    # History test
    results.append(("Conversation History", await test_conversation_history(conv_id)))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 All tests passed! Backend is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Check the output above.")
        print("\nCommon issues:")
        print("  - Is the server running? (uv run python -m app.main)")
        print("  - Is Ollama running? (ollama serve)")
        print("  - Is a model pulled? (ollama pull llama3.2)")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error running tests: {e}")
