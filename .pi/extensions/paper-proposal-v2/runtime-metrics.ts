import { LIMITS } from './types.js';

export type RouteMetricStage = 'LIFECYCLE' | 'DIRECT_DOCUMENT' | 'DELIBERATE' | 'SCIENTIFIC_WORKFLOW' | 'EXISTING_FALLBACK';
export type RouteMetrics = {
 routeSelections: Record<RouteMetricStage, number>;
 bypassedStageSelections: Record<RouteMetricStage, number>;
};
export type RuntimeMetrics={currentParallelValidators:number;maxObservedParallelValidators:number;totalValidatorTasks:number;validatorFailures:number;currentModelCalls:number;maxObservedParallelModelCalls:number;totalModelCalls:number;currentWrites:number;maxObservedParallelWrites:number;totalWrites:number;currentPlannerCalls:number;totalPlannerCalls:number;currentRoleCalls:number;totalRoleCalls:number;totalTutorCalls:number;totalReviewerCalls:number;totalMutations:number;rebuildAttempts:number;rebuildFailures:number;routeMetrics:RouteMetrics};

const routeStages: RouteMetricStage[] = ['LIFECYCLE', 'DIRECT_DOCUMENT', 'DELIBERATE', 'SCIENTIFIC_WORKFLOW', 'EXISTING_FALLBACK'];
function emptyRouteCounts(): Record<RouteMetricStage, number> {
 return Object.fromEntries(routeStages.map(stage => [stage, 0])) as Record<RouteMetricStage, number>;
}
function emptyRouteMetrics(): RouteMetrics {
 return {routeSelections: emptyRouteCounts(), bypassedStageSelections: emptyRouteCounts()};
}
function emptyMetrics(): RuntimeMetrics {
 return {currentParallelValidators:0,maxObservedParallelValidators:0,totalValidatorTasks:0,validatorFailures:0,currentModelCalls:0,maxObservedParallelModelCalls:0,totalModelCalls:0,currentWrites:0,maxObservedParallelWrites:0,totalWrites:0,currentPlannerCalls:0,totalPlannerCalls:0,currentRoleCalls:0,totalRoleCalls:0,totalTutorCalls:0,totalReviewerCalls:0,totalMutations:0,rebuildAttempts:0,rebuildFailures:0,routeMetrics:emptyRouteMetrics()};
}
let metrics:RuntimeMetrics=emptyMetrics();

export function resetRuntimeMetrics(){metrics=emptyMetrics()}
export function getRuntimeMetrics():RuntimeMetrics{return {...metrics,routeMetrics:{routeSelections:{...metrics.routeMetrics.routeSelections},bypassedStageSelections:{...metrics.routeMetrics.bypassedStageSelections}}}}
export function recordRouteMetric(stage: RouteMetricStage, bypassedStages: readonly RouteMetricStage[]): void {
 metrics.routeMetrics.routeSelections[stage]++;
 for (const bypassedStage of bypassedStages) metrics.routeMetrics.bypassedStageSelections[bypassedStage]++;
}
export async function validationTask<T>(run:()=>T|Promise<T>):Promise<T>{if(metrics.currentParallelValidators>=LIMITS.maxParallelValidationTasks)throw new Error('VALIDATION_PARALLELISM_LIMIT');metrics.currentParallelValidators++;metrics.maxObservedParallelValidators=Math.max(metrics.maxObservedParallelValidators,metrics.currentParallelValidators);metrics.totalValidatorTasks++;try{await Promise.resolve();return await run()}catch(error){metrics.validatorFailures++;throw error}finally{metrics.currentParallelValidators--}}
export async function modelCall<T>(kind:'planner'|'tutor'|'reviewer',run:()=>Promise<T>):Promise<T>{if(metrics.currentModelCalls>=LIMITS.maxParallelModelCalls)throw new Error('MODEL_PARALLELISM_LIMIT');metrics.currentModelCalls++;metrics.maxObservedParallelModelCalls=Math.max(metrics.maxObservedParallelModelCalls,metrics.currentModelCalls);metrics.totalModelCalls++;if(kind==='planner'){metrics.currentPlannerCalls++;metrics.totalPlannerCalls++}else{metrics.currentRoleCalls++;metrics.totalRoleCalls++;if(kind==='tutor')metrics.totalTutorCalls++;else metrics.totalReviewerCalls++}try{return await run()}finally{metrics.currentModelCalls--;if(kind==='planner')metrics.currentPlannerCalls--;else metrics.currentRoleCalls--}}
export async function writeTask<T>(run:()=>Promise<T>):Promise<T>{if(metrics.currentWrites>=LIMITS.maxParallelWriteTasks)throw new Error('WRITE_PARALLELISM_LIMIT');metrics.currentWrites++;metrics.maxObservedParallelWrites=Math.max(metrics.maxObservedParallelWrites,metrics.currentWrites);try{const result=await run();metrics.totalWrites++;return result}finally{metrics.currentWrites--}}
export function recordMutation(){metrics.totalMutations++}
export function recordRebuildAttempt(){metrics.rebuildAttempts++}
export function recordRebuildFailure(){metrics.rebuildFailures++}
