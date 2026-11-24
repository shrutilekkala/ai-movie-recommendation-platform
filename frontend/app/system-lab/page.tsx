'use client';
import {useEffect,useState} from 'react';
import Link from 'next/link';
import ModelLab from '@/components/ModelLab';
import RealtimePanel from '@/components/RealtimePanel';
import SearchDebugger from '@/components/SearchDebugger';
import {getCatalogStatus,getRecommendationStatus,getRealtimeSession,getSemanticStatus} from '@/lib/api';
import {CatalogStatus,RecommendationStatus,RealtimeSession,SemanticStatus} from '@/lib/types';

export default function SystemLab(){
 const [model,setModel]=useState<RecommendationStatus|null>(null),[session,setSession]=useState<RealtimeSession|null>(null),[semantic,setSemantic]=useState<SemanticStatus|null>(null),[catalog,setCatalog]=useState<CatalogStatus|null>(null);
 useEffect(()=>{const tick=()=>{getRecommendationStatus().then(setModel).catch(()=>{});getSemanticStatus().then(setSemantic).catch(()=>{});getCatalogStatus().then(setCatalog).catch(()=>{});const t=localStorage.getItem('nexus_token');if(t)getRealtimeSession(t).then(setSession).catch(()=>{})};tick();const id=setInterval(tick,4000);return()=>clearInterval(id)},[]);
 return <main><nav className="nav-shell"><Link className="brand" href="/"><span>N</span>NEXUS</Link><div className="nav-links"><Link href="/">Consumer App</Link><a href="#semantic">Semantic Index</a><a href="#search-debugger">Search Debugger</a><a href="#model-lab">Model Lab</a></div></nav><div className="lab-shell"><div className="lab-hero"><div className="eyebrow">✦ ENGINEERING / ML OBSERVABILITY</div><h1>NEXUS System Lab</h1><p>Cross-catalog engineering view: MovieLens behavior, optional TMDB Telugu enrichment, Qdrant retrieval, Kafka/Redis session intelligence and model metrics.</p></div><section className="semantic-status" id="semantic"><div><div className="eyebrow">VECTOR + CATALOG INTELLIGENCE</div><h2>{semantic?.ready?'Qdrant semantic index is live':'Semantic index waiting'}</h2><p>{semantic?.ready?`${semantic.vectors.toLocaleString()} vectors indexed with ${semantic.embedding_model}.`:semantic?.message||'Start the backend and build the semantic index.'}</p><div className="catalog-stats"><span>Total <b>{catalog?.total?.toLocaleString()??'—'}</b></span><span>MovieLens <b>{catalog?.movielens?.toLocaleString()??'—'}</b></span><span>TMDB-only <b>{catalog?.tmdb?.toLocaleString()??'—'}</b></span><span>Telugu <b>{catalog?.telugu?.toLocaleString()??'—'}</b></span></div></div><span className={semantic?.ready?'live-dot ready':'live-dot'}>{semantic?.ready?'VECTOR READY':'WAITING'}</span></section><SearchDebugger/><RealtimePanel session={session}/><div id="model-lab"><ModelLab status={model}/></div></div></main>
}
