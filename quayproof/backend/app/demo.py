"""Synthetic fixtures authored for this app, never competition ground truth."""
BASE = '''Shipper: Harbor Paper Ltd, 18 Pier Road
Consignee: Cedar Trading Ltd, 7 Market Street
Notify Party: Cedar Trading Ltd, 7 Market Street
Port of Loading: Port Klang
Port of Discharge: Singapore
Container Count: 6 x 40'HC
Gross Weight: 12,500 kg
'''


def demo_cases():
    si = 'SHIPPING INSTRUCTION\n'+BASE
    bl = ('DRAFT BILL OF LADING\n'+BASE).replace('Port of Loading:', 'Load Port:').replace('Container Count: 6 x 40\'HC', 'No. of Containers: 6').replace('12,500 kg', '12.5 MT')
    request = 'Please compare the attached draft BL against the SI and verify all seven fields.'
    return [
        ('demo-01', 'A clean comparison', request, [('instruction.txt',si),('draft.txt',bl)]),
        ('demo-02', 'A discrepancy to catch', request, [('instruction.txt',si),('draft.txt',bl.replace('12.5 MT','12.8 MT'))]),
        ('demo-03', 'A value that needs review', request, [('instruction.txt',si),('draft.txt',bl.replace('12.5 MT','TBC'))]),
        ('demo-04', 'The missing draft', request, [('instruction.txt',si)]),
        ('demo-05', 'Wrong document attached', request, [('instruction.txt',si),('draft.txt','COMMERCIAL INVOICE\nAmount due: USD 3000')]),
        ('demo-06', 'BL check — old subject', 'Please prepare a new shipping instruction for this shipment.\n\nOn Monday someone wrote:\n> Please compare the old BL.', []),
        ('demo-07', 'Invoice clarification', 'Can you explain the invoice charges for this shipment?', []),
        ('demo-08', 'Operations update', 'The vessel arrival has been rescheduled. Please update the operations team.', []),
        ('demo-09', 'A prize offer', 'You won the lottery! Claim your prize now.', []),
    ]
