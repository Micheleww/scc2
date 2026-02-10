#!/usr/bin/env python3
"""
Unit Test for SSEClient Queue Overflow Handling

This script directly tests the SSEClient class's queue overflow handling
without relying on the full server-client interaction.
"""

import sys
import time
import unittest
from unittest.mock import MagicMock

# Add the current directory to path to import the module
sys.path.insert(0, "d:\\quantsys\\tools\\exchange_server")

# Import the SSEClient class
from main import SSEClient


class TestSSEClientQueueOverflow(unittest.TestCase):
    """Test SSEClient queue overflow handling"""

    def setUp(self):
        """Set up test fixtures"""
        # Create a mock response object
        self.mock_response = MagicMock()

        # Create an SSEClient with small queue size for testing
        self.max_queue_size = 5
        self.client = SSEClient(
            response=self.mock_response,
            ip="127.0.0.1",
            trace_id="test-trace-id",
            client_id="test-client-id",
            max_queue_size=self.max_queue_size,
        )

    def test_initial_queue_state(self):
        """Test initial queue state"""
        self.assertEqual(len(self.client.message_queue), 0)
        self.assertFalse(self.client.queue_overflow)

    def test_queue_add_normal(self):
        """Test adding messages to queue normally"""
        # Add messages within queue limit
        for i in range(self.max_queue_size):
            result = self.client.add_message(f"test message {i}", event_type="test")
            self.assertEqual(result["status"], "added")
            self.assertEqual(result["action"], "queue_added")

        # Check queue size
        self.assertEqual(len(self.client.message_queue), self.max_queue_size)
        self.assertFalse(self.client.queue_overflow)

    def test_queue_overflow_discard(self):
        """Test queue overflow handling - discard non-critical message"""
        # Fill the queue with non-critical messages
        for i in range(self.max_queue_size):
            self.client.add_message(f"non-critical {i}", event_type="test", is_critical=False)

        # Add one more non-critical message - should be discarded
        result = self.client.add_message("overflow message", event_type="test", is_critical=False)

        # Check result
        self.assertEqual(result["status"], "discarded")
        self.assertEqual(result["action"], "queue_full_non_critical_discarded")
        self.assertTrue(self.client.queue_overflow)

        # Queue should still be at max size
        self.assertEqual(len(self.client.message_queue), self.max_queue_size)

    def test_queue_overflow_remove_oldest(self):
        """Test queue overflow handling - remove oldest non-critical message"""
        # Fill the queue with a mix of critical and non-critical messages
        for i in range(self.max_queue_size - 1):
            self.client.add_message(f"non-critical {i}", event_type="test", is_critical=False)

        # Add a critical message
        self.client.add_message("critical message", event_type="test", is_critical=True)

        # Now add another critical message - should remove oldest non-critical
        result = self.client.add_message("new critical", event_type="test", is_critical=True)

        # Check result
        self.assertEqual(result["status"], "added")
        self.assertEqual(result["action"], "removed_oldest_non_critical")
        self.assertTrue(self.client.queue_overflow)

        # Queue should still be at max size
        self.assertEqual(len(self.client.message_queue), self.max_queue_size)

    def test_queue_processing(self):
        """Test queue processing"""
        # Fill the queue
        for i in range(self.max_queue_size):
            self.client.add_message(f"message {i}", event_type="test")

        # Process all messages
        processed = []
        while self.client.message_queue:
            msg = self.client.message_queue.popleft()
            processed.append(msg)

        # Check all messages were processed
        self.assertEqual(len(processed), self.max_queue_size)

        # Check queue is empty
        self.assertEqual(len(self.client.message_queue), 0)

    def test_heartbeat_delay_detection(self):
        """Test heartbeat delay detection"""
        # Update heartbeat sent time
        self.client.update_heartbeat_sent()

        # Wait a bit
        time.sleep(0.1)

        # Update again - should detect delay
        self.client.update_heartbeat_sent()

        # Check delay was recorded
        self.assertGreater(self.client.heartbeat_delay, 0)

    def test_proxy_buffering_detection(self):
        """Test proxy buffering detection"""
        # Set last buffer flush to long ago
        self.client.last_buffer_flush = time.time() - 70  # 70 seconds ago

        # Add some messages to queue
        for i in range(3):
            self.client.add_message(f"test {i}", event_type="test")

        # Detect proxy buffering
        proxy_buffering = self.client.detect_proxy_buffering()

        # Should detect proxy buffering risk
        self.assertTrue(proxy_buffering)
        self.assertTrue(self.client.proxy_buffering_risk)


if __name__ == "__main__":
    print("Running SSEClient Queue Overflow Unit Tests...")
    print("=" * 60)

    # Run all tests
    unittest.main(verbosity=2)
