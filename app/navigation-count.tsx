"use client";
import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
const CountContext=createContext<{count:{path:string;value:number}|null;setCount:(value:{path:string;value:number}|null)=>void}>({count:null,setCount:()=>{}});
export function NavigationCountProvider({children}:{children:ReactNode}) {
 const [count,setCount]=useState<{path:string;value:number}|null>(null);
 return <CountContext.Provider value={{count,setCount}}>{children}</CountContext.Provider>;
}
export function useNavigationCount() {return useContext(CountContext).count}
export function usePageCount(path:string,value:number|null) {
 const {setCount}=useContext(CountContext);
 useEffect(()=>{setCount(value===null?null:{path,value});return ()=>setCount(null)},[path,value,setCount]);
}
