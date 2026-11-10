import unittest
import pandas as pd
from detectors import detect

class SQLTests(unittest.TestCase):
    def test_relations_duplicates_and_empty_values(self):
        master = pd.DataFrame({'Id Proveedor':['1','2','3','3'], 'Cuenta':['001','001','002','003']})
        payments = pd.DataFrame({'VENDOR_ID':['1','2','3','9','3','1'],
                                 'BANK_ACCOUNT_NUM':['001','999','003','001','','001'],
                                 'UUID':['dup','DUP','ok','unique','','']})
        flags = detect(payments, master)
        self.assertEqual(flags.index[flags.A].tolist(), [3])
        self.assertEqual(flags.index[flags.B].tolist(), [1])
        self.assertEqual(flags.index[flags.C].tolist(), [0,1,5])
        self.assertEqual(flags.index[flags.D].tolist(), [0,1])

if __name__ == '__main__':
    unittest.main()
