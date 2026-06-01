"""Load testing script for BARROW.AI admin knowledge endpoints.

Tests:
1. List documents (with/without indexes)
2. Concurrent uploads
3. Get document details
4. Update operations
5. Delete operations

Usage:
    python test_load_knowledge.py --token YOUR_TOKEN --url http://localhost:8000
"""

import asyncio
import httpx
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import json


class LoadTester:
    """Load testing suite for admin knowledge endpoints."""
    
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}
        self.results = {}
        self.uploaded_docs = []
    
    async def test_list_documents(self):
        """Test GET /admin/knowledge with various filters."""
        print("\n📋 Test 1: List Documents")
        print("-" * 60)
        
        async with httpx.AsyncClient(headers=self.headers) as client:
            test_cases = [
                {"name": "List 50 (default)", "params": {}},
                {"name": "List 100", "params": {"limit": 100}},
                {"name": "List with offset", "params": {"limit": 50, "offset": 50}},
                {"name": "Filter by status=active", "params": {"status": "active"}},
                {"name": "Filter by language=en", "params": {"language": "en"}},
            ]
            
            test_results = []
            for test_case in test_cases:
                try:
                    start = time.time()
                    response = await client.get(
                        f"{self.base_url}/admin/knowledge",
                        params=test_case["params"],
                        timeout=30.0
                    )
                    elapsed = time.time() - start
                    
                    status = "✓" if response.status_code == 200 else "✗"
                    print(f"  {status} {test_case['name']}: {elapsed*1000:.1f}ms (status: {response.status_code})")
                    
                    if response.status_code == 200:
                        data = response.json()
                        print(f"    Found {data.get('total', 0)} documents")
                    
                    test_results.append({
                        "test": test_case["name"],
                        "elapsed_ms": elapsed * 1000,
                        "status_code": response.status_code,
                        "success": response.status_code == 200
                    })
                except Exception as e:
                    print(f"  ✗ {test_case['name']}: ERROR - {str(e)}")
                    test_results.append({
                        "test": test_case["name"],
                        "error": str(e),
                        "success": False
                    })
            
            self.results["list_documents"] = test_results
    
    async def test_concurrent_uploads(self):
        """Test concurrent document uploads."""
        print("\n📤 Test 2: Concurrent Uploads")
        print("-" * 60)
        
        # Create test files
        test_files = []
        for i in range(5):
            content = f"Test document {i}\n" + ("Lorem ipsum dolor sit amet. " * 100)
            test_files.append({
                "name": f"test_{i}.txt",
                "content": content.encode("utf-8"),
                "title": f"Test Document {i}"
            })
        
        async with httpx.AsyncClient(headers=self.headers) as client:
            # Test different concurrency levels
            for concurrency in [1, 3, 5]:
                print(f"\n  Testing with {concurrency} concurrent uploads...")
                
                start = time.time()
                tasks = []
                
                for file_data in test_files:
                    task = client.post(
                        f"{self.base_url}/admin/knowledge",
                        files={"file": (file_data["name"], file_data["content"])},
                        data={"title": file_data["title"]},
                        timeout=30.0
                    )
                    tasks.append(task)
                    
                    if len(tasks) >= concurrency:
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        tasks = []
                
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                
                elapsed = time.time() - start
                
                # Count successes
                success_count = sum(
                    1 for r in results 
                    if isinstance(r, httpx.Response) and r.status_code == 201
                )
                
                print(f"    {success_count}/{len(test_files)} uploads successful")
                print(f"    Total time: {elapsed:.2f}s ({elapsed/len(test_files):.2f}s per upload)")
                
                # Store document IDs for later tests
                for r in results:
                    if isinstance(r, httpx.Response) and r.status_code == 201:
                        doc = r.json()
                        self.uploaded_docs.append(doc.get("document_id"))
                
                self.results["concurrent_uploads"] = {
                    "concurrency": concurrency,
                    "total_time_s": elapsed,
                    "success_count": success_count,
                    "total_tests": len(test_files),
                    "avg_time_per_upload_s": elapsed / len(test_files)
                }
    
    async def test_get_document_details(self):
        """Test GET /admin/knowledge/{id}."""
        print("\n📄 Test 3: Get Document Details")
        print("-" * 60)
        
        if not self.uploaded_docs:
            print("  ⚠️  No documents uploaded yet, skipping...")
            return
        
        async with httpx.AsyncClient(headers=self.headers) as client:
            times = []
            for doc_id in self.uploaded_docs[:3]:  # Test first 3
                try:
                    start = time.time()
                    response = await client.get(
                        f"{self.base_url}/admin/knowledge/{doc_id}",
                        timeout=30.0
                    )
                    elapsed = time.time() - start
                    
                    status = "✓" if response.status_code == 200 else "✗"
                    print(f"  {status} Get {doc_id[:8]}...: {elapsed*1000:.1f}ms")
                    times.append(elapsed)
                except Exception as e:
                    print(f"  ✗ Get {doc_id[:8]}...: ERROR - {str(e)}")
            
            if times:
                avg_time = sum(times) / len(times)
                print(f"\n  Average response time: {avg_time*1000:.1f}ms")
                self.results["get_document"] = {
                    "avg_time_ms": avg_time * 1000,
                    "min_time_ms": min(times) * 1000,
                    "max_time_ms": max(times) * 1000
                }
    
    async def test_update_documents(self):
        """Test PUT /admin/knowledge/{id}."""
        print("\n✏️  Test 4: Update Document")
        print("-" * 60)
        
        if not self.uploaded_docs:
            print("  ⚠️  No documents uploaded yet, skipping...")
            return
        
        async with httpx.AsyncClient(headers=self.headers) as client:
            for doc_id in self.uploaded_docs[:2]:  # Update first 2
                try:
                    start = time.time()
                    response = await client.put(
                        f"{self.base_url}/admin/knowledge/{doc_id}",
                        data={"title": f"Updated - {datetime.utcnow().isoformat()}"},
                        timeout=30.0
                    )
                    elapsed = time.time() - start
                    
                    status = "✓" if response.status_code == 200 else "✗"
                    print(f"  {status} Update {doc_id[:8]}...: {elapsed*1000:.1f}ms")
                except Exception as e:
                    print(f"  ✗ Update {doc_id[:8]}...: ERROR - {str(e)}")
    
    async def test_delete_documents(self):
        """Test DELETE /admin/knowledge/{id}."""
        print("\n🗑️  Test 5: Delete Documents")
        print("-" * 60)
        
        if not self.uploaded_docs:
            print("  ⚠️  No documents uploaded yet, skipping...")
            return
        
        async with httpx.AsyncClient(headers=self.headers) as client:
            for doc_id in self.uploaded_docs[:2]:  # Delete first 2
                try:
                    start = time.time()
                    response = await client.delete(
                        f"{self.base_url}/admin/knowledge/{doc_id}",
                        timeout=30.0
                    )
                    elapsed = time.time() - start
                    
                    status = "✓" if response.status_code == 200 else "✗"
                    print(f"  {status} Delete {doc_id[:8]}...: {elapsed*1000:.1f}ms")
                except Exception as e:
                    print(f"  ✗ Delete {doc_id[:8]}...: ERROR - {str(e)}")
    
    async def run_all_tests(self):
        """Run all load tests."""
        print("\n" + "="*60)
        print("🧪 BARROW.AI Admin Knowledge Endpoints - Load Test Suite")
        print("="*60)
        print(f"Base URL: {self.base_url}")
        print(f"Start Time: {datetime.utcnow().isoformat()}")
        
        try:
            await self.test_list_documents()
            await self.test_concurrent_uploads()
            await self.test_get_document_details()
            await self.test_update_documents()
            await self.test_delete_documents()
        except Exception as e:
            print(f"\n❌ Test suite failed: {str(e)}")
            raise
        
        print("\n" + "="*60)
        print("✅ All tests completed")
        print("="*60)
        
        # Print summary
        self._print_summary()
    
    def _print_summary(self):
        """Print test results summary."""
        print("\n📊 Summary:")
        print(json.dumps(self.results, indent=2, default=str))


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Load test BARROW.AI admin knowledge endpoints"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--token",
        required=True,
        help="JWT authentication token"
    )
    
    args = parser.parse_args()
    
    tester = LoadTester(args.url, args.token)
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
