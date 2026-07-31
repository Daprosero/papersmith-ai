import { LIMITS } from './types.js';

export type RouteMetricStage = 'LIFECYCLE' | 'DIRECT_DOCUMENT' | 'CHAT_DELIBERATION' | 'DRAFT_MATERIALIZATION' | 'MAINTENANCE' | 'SCIENTIFIC_WORKFLOW' | 'EXISTING_FALLBACK';
export type RouteMetrics = {
 routeSelections: Record<RouteMetricStage, number>;
 bypassedStageSelections: Record<RouteMetricStage, number>;
};
export type ScientificMetricKind='entry'|'blocked'|'recovery_required'|'materialization_blocked'|'materialization_recovery_required'|'materialization_retry'|'recovery_diagnostic';
export type ScientificOperationalMetrics=Record<ScientificMetricKind,number>;
export type LifecycleMetricKind='withdrawal_committed'|'withdrawal_rejected'|'restore_committed'|'restore_rejected';
export type LifecycleOperationalMetrics=Record<LifecycleMetricKind,number>;
export type RuntimeMetrics={currentParallelValidators:number;maxObservedParallelValidators:number;totalValidatorTasks:number;validatorFailures:number;currentModelCalls:number;maxObservedParallelModelCalls:number;totalModelCalls:number;currentWrites:number;maxObservedParallelWrites:number;totalWrites:number;currentPlannerCalls:number;totalPlannerCalls:number;currentRoleCalls:number;totalRoleCalls:number;totalTutorCalls:number;totalReviewerCalls:number;totalMutations:number;rebuildAttempts:number;rebuildFailures:number;routeMetrics:RouteMetrics;scientificMetrics:ScientificOperationalMetrics;lifecycleMetrics:LifecycleOperationalMetrics};

const routeStages: RouteMetricStage[] = ['LIFECYCLE', 'DIRECT_DOCUMENT', 'CHAT_DELIBERATION', 'DRAFT_MATERIALIZATION', 'MAINTENANCE', 'SCIENTIFIC_WORKFLOW', 'EXISTING_FALLBACK'];
function emptyRouteCounts(): Record<RouteMetricStage, number> {
 return Object.fromEntries(routeStages.map(stage => [stage, 0])) as Record<RouteMetricStage, number>;
}
function emptyRouteMetrics(): RouteMetrics {
 return {routeSelections: emptyRouteCounts(), bypassedStageSelections: emptyRouteCounts()};
}
function emptyScientificMetrics(): ScientificOperationalMetrics { return {entry:0,blocked:0,recovery_required:0,materialization_blocked:0,materialization_recovery_required:0,materialization_retry:0,recovery_diagnostic:0}; }
function emptyLifecycleMetrics(): LifecycleOperationalMetrics { return {withdrawal_committed:0,withdrawal_rejected:0,restore_committed:0,restore_rejected:0}; }
function emptyMetrics(): RuntimeMetrics {
 return {currentParallelValidators:0,maxObservedParallelValidators:0,totalValidatorTasks:0,validatorFailures:0,currentModelCalls:0,maxObservedParallelModelCalls:0,totalModelCalls:0,currentWrites:0,maxObservedParallelWrites:0,totalWrites:0,currentPlannerCalls:0,totalPlannerCalls:0,currentRoleCalls:0,totalRoleCalls:0,totalTutorCalls:0,totalReviewerCalls:0,totalMutations:0,rebuildAttempts:0,rebuildFailures:0,routeMetrics:emptyRouteMetrics(),scientificMetrics:emptyScientificMetrics(),lifecycleMetrics:emptyLifecycleMetrics()};
}
let metrics:RuntimeMetrics=emptyMetrics();

export function resetRuntimeMetrics(){metrics=emptyMetrics()}
export function getRuntimeMetrics():RuntimeMetrics{return {...metrics,routeMetrics:{routeSelections:{...metrics.routeMetrics.routeSelections},bypassedStageSelections:{...metrics.routeMetrics.bypassedStageSelections}},scientificMetrics:{...metrics.scientificMetrics},lifecycleMetrics:{...metrics.lifecycleMetrics}}}
export function recordRouteMetric(stage: RouteMetricStage, bypassedStages: readonly RouteMetricStage[]): void {
 metrics.routeMetrics.routeSelections[stage]++;
 for (const bypassedStage of bypassedStages) metrics.routeMetrics.bypassedStageSelections[bypassedStage]++;
}
export async function validationTask<T>(run:()=>T|Promise<T>):Promise<T>{if(metrics.currentParallelValidators>=LIMITS.maxParallelValidationTasks)throw new Error('VALIDATION_PARALLELISM_LIMIT');metrics.currentParallelValidators++;metrics.maxObservedParallelValidators=Math.max(metrics.maxObservedParallelValidators,metrics.currentParallelValidators);metrics.totalValidatorTasks++;try{await Promise.resolve();return await run()}catch(error){metrics.validatorFailures++;throw error}finally{metrics.currentParallelValidators--}}
// Ambient-model paradigm (design `sdd/paper-proposal-ambient-model`, SLICE 2): the
// `currentModelCalls>=LIMITS.maxParallelModelCalls` throttle (a real-API-cost cap) was
// removed -- role-port invocations (ambient-echoed or scripted-test-injected) are no
// longer real network calls to bound. The counting itself STAYS: `modelCalls`/
// `plannerCalls`/`tutorCalls`/`reviewerCalls` are still real, observable result fields
// many tests assert on.
export async function modelCall<T>(kind:'planner'|'tutor'|'reviewer',run:()=>Promise<T>):Promise<T>{metrics.currentModelCalls++;metrics.maxObservedParallelModelCalls=Math.max(metrics.maxObservedParallelModelCalls,metrics.currentModelCalls);metrics.totalModelCalls++;if(kind==='planner'){metrics.currentPlannerCalls++;metrics.totalPlannerCalls++}else{metrics.currentRoleCalls++;metrics.totalRoleCalls++;if(kind==='tutor')metrics.totalTutorCalls++;else metrics.totalReviewerCalls++}try{return await run()}finally{metrics.currentModelCalls--;if(kind==='planner')metrics.currentPlannerCalls--;else metrics.currentRoleCalls--}}
export async function writeTask<T>(run:()=>Promise<T>):Promise<T>{if(metrics.currentWrites>=LIMITS.maxParallelWriteTasks)throw new Error('WRITE_PARALLELISM_LIMIT');metrics.currentWrites++;metrics.maxObservedParallelWrites=Math.max(metrics.maxObservedParallelWrites,metrics.currentWrites);try{const result=await run();metrics.totalWrites++;return result}finally{metrics.currentWrites--}}
export function recordScientificMetric(kind:ScientificMetricKind){metrics.scientificMetrics[kind]++}
export function recordLifecycleMetric(kind:LifecycleMetricKind){metrics.lifecycleMetrics[kind]++}
export function recordMutation(){metrics.totalMutations++}
export function recordRebuildAttempt(){metrics.rebuildAttempts++}
export function recordRebuildFailure(){metrics.rebuildFailures++}
