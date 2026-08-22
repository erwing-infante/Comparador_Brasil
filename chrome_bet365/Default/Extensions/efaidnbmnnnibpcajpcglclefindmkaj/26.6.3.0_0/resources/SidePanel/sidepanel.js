/*************************************************************************
* ADOBE CONFIDENTIAL
* ___________________
*
*  Copyright 2015 Adobe Systems Incorporated
*  All Rights Reserved.
*
* NOTICE:  All information contained herein is, and remains
* the property of Adobe Systems Incorporated and its suppliers,
* if any.  The intellectual and technical concepts contained
* herein are proprietary to Adobe Systems Incorporated and its
* suppliers and are protected by all applicable intellectual property laws,
* including trade secret and or copyright laws.
* Dissemination of this information or reproduction of this material
* is strictly forbidden unless prior written permission is obtained
* from Adobe Systems Incorporated.
**************************************************************************/
import{dcLocalStorage as e}from"../../common/local-storage.js";import{SIDE_PANEL_HASH_ROUTES as t}from"../../common/constant.js";import{util as o}from"../../browser/js/content-util.js";import{checkCdnConnectivity as n}from"../../common/util.js";import{createSendAnalytics as r,getSidePanelTabId as m,isHomeShellRoute as a}from"./sidePanelUtil.js";import{fetchAndSendHtmlContent as i}from"./htmlContentFetcher.js";import{getGenAiPrerenderState as s,shouldShowTrefoilLoader as d,showTrefoilLoader as l}from"./loaderUIHelper.js";import{Cdn as c}from"./cdn.js";import{initHomeMode as p}from"./home.js";import{initOfflineMode as f}from"./offline.js";import{registerHostedShellListeners as I}from"./shell-listeners.js";const h=Date.now();await e.init();const E=e.getItem("isSidePanelHomeEnabled"),u=document.getElementById("tooltipTextEnabled");E&&u&&(u.id="tooltipTextEnabledHome"),o.translateElementsByAppLocale(".translate");let w=e.getItem("touchpoint");e.removeItem("touchpoint");let S=e.getItem("hashRoute");e.removeItem("hashRoute"),w||(w="ExtensionAction",S=t.HOME),E||(S=t.SIDE_PANEL);const j=a(S),b=await s(S,w);d(b)&&l(),b?.showPreRendered&&(e=>{const t=document.createElement("iframe");t.id="sidepanelPreRendered",t.title="Adobe Chatbot",t.srcdoc=e,document.body.appendChild(t)})(b.anonGenAISSRHtml);const A=e.getItem("sidepanelUrl");if(A){await n(A)?j?await p(h,S,w):await async function(e,o,n){const a=m(),s=r(a);s(`DCBrowserExt:SidePanel:Opened:${o||"Unspecified"}`);const d=new c({initTimeStamp:e,hostedHashRoute:t.SIDE_PANEL,touchpoint:o,anonGenAISSRHtml:n?.anonGenAISSRHtml,onIframeLoad:()=>s(`DCBrowserExt:SidePanel:IframeLoaded:${o}`),onIframeError:()=>s(`DCBrowserExt:SidePanel:IframeLoadError:${o}`)});I({cdn:d,sendAnalytics:s,tabId:a,touchpoint:o}),await i({cdn:d,tabId:d.tabId,touchpoint:o})}(h,w,b):f(h)}