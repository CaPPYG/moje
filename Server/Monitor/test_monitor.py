import json
import unittest
from app import app


class TestSystemMonitor(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_health_endpoint(self):
        res = self.client.get('/health')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data.get('status'), 'healthy')

    def test_system_status_endpoint(self):
        res = self.client.get('/api/system-status')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)

        self.assertEqual(data.get('status'), 'ok')
        self.assertTrue(data.get('online'))

        # Overenie štruktúry CPU
        self.assertIn('cpu', data)
        self.assertIn('percent', data['cpu'])
        self.assertIn('cores', data['cpu'])
        self.assertIsInstance(data['cpu']['percent'], (int, float))

        # Overenie pamäte (RAM)
        self.assertIn('memory', data)
        self.assertIn('total_gb', data['memory'])
        self.assertIn('used_gb', data['memory'])
        self.assertIn('percent', data['memory'])

        # Overenie disku
        self.assertIn('disk', data)
        self.assertIn('total_gb', data['disk'])
        self.assertIn('used_gb', data['disk'])
        self.assertIn('percent', data['disk'])

        # Overenie sieťových metrík
        self.assertIn('network', data)
        self.assertIn('egress_mb', data['network'])
        self.assertIn('egress_gb', data['network'])
        self.assertIn('ingress_mb', data['network'])
        self.assertIn('ingress_gb', data['network'])
        self.assertIn('rate_out_human', data['network'])
        self.assertIn('rate_in_human', data['network'])
        self.assertIn('rate_summary', data['network'])

        # Overenie uptime
        self.assertIn('uptime', data)
        self.assertIn('human', data['uptime'])


if __name__ == '__main__':
    unittest.main()
