'use client';
import {Database, Gauge, Users, Sparkles, Trophy} from 'lucide-react';
import {RecommendationStatus} from '@/lib/types';

const labels:Record<string,string>={
 popularity:'Popularity',collaborative:'Item-Item CF',content_based:'Content-Based',hybrid:'Fixed Hybrid',learned_hybrid:'Learned Hybrid'
};
export default function ModelLab({status}:{status:RecommendationStatus|null}){
 if(!status)return null;
 const rows=Object.entries(status.model_comparison??{});
 const w=status.learned_weights??{};
 return <section className="model-lab" id="model-lab">
   <div className="model-lab-head"><div><div className="eyebrow">✦ REAL DATA / MODEL LAB</div><h2>{status.ready?'Hybrid recommender is live':'MovieLens is ready to import'}</h2><p>{status.message}</p></div><span className={status.ready?'live-dot ready':'live-dot'}>{status.ready?'MODEL READY':'WAITING FOR DATA'}</span></div>
   <div className="metric-grid">
    <Metric icon={<Database size={16}/>} label="Ratings" value={status.ratings.toLocaleString()}/>
    <Metric icon={<Sparkles size={16}/>} label="Movies" value={status.movies.toLocaleString()}/>
    <Metric icon={<Users size={16}/>} label="Real users" value={status.users.toLocaleString()}/>
    <Metric icon={<Gauge size={16}/>} label="Winner HitRate@10" value={status.metrics.hit_rate_at_10==null?'—':`${(status.metrics.hit_rate_at_10*100).toFixed(1)}%`}/>
    <Metric icon={<Gauge size={16}/>} label="Winner NDCG@10" value={status.metrics.ndcg_at_10==null?'—':status.metrics.ndcg_at_10.toFixed(3)}/>
   </div>
   {rows.length>0&&<>
    <div className="model-table-wrap"><table className="model-table"><thead><tr><th>Model</th><th>HitRate@10</th><th>Recall@10</th><th>NDCG@10</th><th>Users</th></tr></thead><tbody>{rows.map(([name,m])=><tr key={name} className={status.winner===name?'winner-row':''}><td>{status.winner===name&&<Trophy size={14}/>} {labels[name]??name}</td><td>{m.hit_rate_at_10==null?'—':`${(m.hit_rate_at_10*100).toFixed(2)}%`}</td><td>{m.recall_at_10==null?'—':`${(m.recall_at_10*100).toFixed(2)}%`}</td><td>{m.ndcg_at_10==null?'—':m.ndcg_at_10.toFixed(4)}</td><td>{m.evaluated_users}</td></tr>)}</tbody></table></div>
    <div className="weight-strip"><span>LEARNED RANKING WEIGHTS</span><b>Collaborative {(100*(w.collaborative??0)).toFixed(0)}%</b><b>Content {(100*(w.content??0)).toFixed(0)}%</b><b>Popularity {(100*(w.popularity??0)).toFixed(0)}%</b></div>
   </>}
   {!status.ready&&<code className="import-command">docker compose exec backend python -m app.scripts.import_movielens</code>}
 </section>
}
function Metric({icon,label,value}:{icon:React.ReactNode;label:string;value:string}){return <div className="metric-card"><span>{icon}</span><div><small>{label}</small><strong>{value}</strong></div></div>}
