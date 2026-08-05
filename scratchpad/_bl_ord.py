bl_ES={1:7579.32,2:7427.49,3:7566.74,4:7484.72,5:7835.74,6:7471.50,7:7246.19,8:7279.90,9:7603.29,10:7615.64}
bl_NQ={1:29090.25,2:28504.10,3:29463.36,4:29228.17,5:28892.27,6:28327.97,7:29300.79,8:27936.18,9:29048.15,10:29489.09}
spot={'ES':7494.75,'NQ':28768.25}
for name,bl,sp in [('ES',bl_ES,spot['ES']),('NQ',bl_NQ,spot['NQ'])]:
    print('====',name,'spot',sp)
    rows=[]
    for i in range(1,11):
        d=bl[i]-sp
        rows.append((i,bl[i],d,abs(d),'above' if d>0 else 'below'))
    order=sorted(rows,key=lambda r:r[3])
    rankmap={r[0]:k+1 for k,r in enumerate(order)}
    nab=sum(1 for r in rows if r[2]>0)
    print('  above=%d below=%d'%(nab,10-nab))
    for r in rows:
        print('  bl_%-2d %9.2f  %+9.2f  |d|=%7.2f  %-5s  rank_%d'%(r[0],r[1],r[2],r[3],r[4],rankmap[r[0]]))
    print('  --- sorted by value low->high:')
    for r in sorted(rows,key=lambda x:x[1]):
        print('    bl_%-2d %9.2f %s'%(r[0],r[1],r[4]))
    print('  odd idx sides :',[ (r[0],r[4]) for r in rows if r[0]%2==1])
    print('  even idx sides:',[ (r[0],r[4]) for r in rows if r[0]%2==0])
