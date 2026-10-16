// Temporary in-memory PostgreSQL engine for migration tests, never connects to a server.
const {PGlite}=require('@electric-sql/pglite');
const {createInterface}=require('node:readline');
(async()=>{
 const db=new PGlite();await db.waitReady;
 for await(const line of createInterface({input:process.stdin})){
  try{const {sql}=JSON.parse(line);const result=await db.query(sql);process.stdout.write(JSON.stringify({rows:result.rows})+'\n');}
  catch(error){process.stdout.write(JSON.stringify({error:error.message})+'\n');}
 }
 await db.close();
})().catch(e=>{console.error(e);process.exit(1);});
