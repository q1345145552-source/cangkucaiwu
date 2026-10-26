// Legacy regression harness isolates its original behaviour. Round04 tests compile
// the actual CostIdentity module separately; this adapter is not evidence for it.
const emptyCost=()=>({supplier_id:0,invoice:{issuer_identifier:'',series:'',number:'',verified:false}});
module.exports={emptyCost,useCostIdentity:()=>({value:emptyCost(),setValue(){},reset(){},async edit(){},payload:()=>({}),capture:()=>false,dialog:null,fields:null})};
