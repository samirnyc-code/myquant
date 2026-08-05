import json,math
d=json.load(open('scratchpad/bl_live_pull.json'))
bl={'ES':[7579.32,7427.49,7566.74,7484.72,7835.74,7471.50,7246.19,7279.90,7603.29,7615.64],
    'NQ':[29090.25,28504.10,29463.36,29228.17,28892.27,28327.97,29300.79,27936.18,29048.15,29489.09]}
spot={'ES':7494.75,'NQ':28768.25}
for sym in ['ES','NQ']:
    iv=d['vi_%s'%sym]['iv']
    print('====',sym,'spot',spot[sym])
    print('  iv_0dte',round(iv['iv_0dte_50d'],4),'iv_1m',round(iv['iv_1m_50d'],4),'iv_3m',round(iv['iv_3m_50d'],4),'hv_1m',round(iv['hv_1m'],4))
    sp=spot[sym]
    lo=min(bl[sym]); hi=max(bl[sym])
    print('  BL band: low %.2f (%.2f%%)  high %.2f (+%.2f%%)'%(lo,(lo/sp-1)*100,hi,(hi/sp-1)*100))
    for horizon,dte in [('0dte',1),('1w',5),('1m',21),('3m',63)]:
        ivkey={'0dte':'iv_0dte_50d','1w':'iv_1m_50d','1m':'iv_1m_50d','3m':'iv_3m_50d'}[horizon]
        s=iv[ivkey]; T=dte/252.0; sig=s*math.sqrt(T)
        print('    %-4s(dte%2d, iv=%.3f): 1sig=%.2f%%  band %.2f .. %.2f'%(horizon,dte,s,sig*100,sp*(1-sig),sp*(1+sig)))
