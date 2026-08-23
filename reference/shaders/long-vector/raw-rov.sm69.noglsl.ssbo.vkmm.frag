; SPIR-V
; Version: 1.6
; Generator: Unknown(30017); 21022
; Bound: 65
; Schema: 0
OpCapability Shader
OpCapability VulkanMemoryModel
OpCapability FragmentShaderPixelInterlockEXT
OpCapability LongVectorEXT
OpExtension "SPV_EXT_fragment_shader_interlock"
OpExtension "SPV_EXT_long_vector"
OpMemoryModel Logical Vulkan
OpEntryPoint Fragment %3 "main" %10 %14 %18
OpExecutionMode %3 OriginUpperLeft
OpExecutionMode %3 PixelInterlockOrderedEXT
OpName %3 "main"
OpName %8 "SSBO"
OpName %12 "SSBO"
OpName %18 "SV_Position"
OpName %29 "ByteAddressMask"
OpName %27 "index"
OpName %28 "stride"
OpDecorate %7 ArrayStride 64
OpMemberDecorate %8 0 Offset 0
OpDecorate %8 Block
OpDecorate %10 DescriptorSet 0
OpDecorate %10 Binding 0
OpDecorate %10 NonWritable
OpDecorate %10 Restrict
OpDecorate %11 ArrayStride 64
OpMemberDecorate %12 0 Offset 0
OpDecorate %12 Block
OpDecorate %14 DescriptorSet 0
OpDecorate %14 Binding 0
OpDecorate %14 NonReadable
OpDecorate %18 BuiltIn FragCoord
%1 = OpTypeVoid
%2 = OpTypeFunction %1
%5 = OpTypeInt 32 0
%6 = OpTypeVector %5 16
%7 = OpTypeRuntimeArray %6
%8 = OpTypeStruct %7
%9 = OpTypePointer StorageBuffer %8
%10 = OpVariable %9 StorageBuffer
%11 = OpTypeRuntimeArray %6
%12 = OpTypeStruct %11
%13 = OpTypePointer StorageBuffer %12
%14 = OpVariable %13 StorageBuffer
%15 = OpTypeFloat 32
%16 = OpTypeVector %15 4
%17 = OpTypePointer Input %16
%18 = OpVariable %17 Input
%19 = OpTypePointer Input %15
%21 = OpConstant %5 0
%25 = OpConstant %5 6
%26 = OpTypeFunction %5 %5 %5
%32 = OpConstant %5 4294967295
%36 = OpConstant %5 64
%37 = OpTypePointer StorageBuffer %6
%41 = OpConstant %5 1
%42 = OpConstantComposite %6 %41 %41 %41 %41 %41 %41 %41 %41 %41 %41 %41 %41 %41 %41 %41 %41
%62 = OpConstant %5 5
%3 = OpFunction %1 None %2
%4 = OpLabel
OpBranch %63
%63 = OpLabel
%20 = OpAccessChain %19 %18 %21
%22 = OpLoad %15 %20
%23 = OpConvertFToU %5 %22
%24 = OpShiftLeftLogical %5 %23 %25
%35 = OpFunctionCall %5 %29 %23 %36
%38 = OpAccessChain %37 %10 %21 %35
%39 = OpLoad %6 %38
%40 = OpIAdd %6 %39 %42
%43 = OpFunctionCall %5 %29 %23 %36
%44 = OpCompositeExtract %5 %40 0
%45 = OpCompositeExtract %5 %40 1
%46 = OpCompositeExtract %5 %40 2
%47 = OpCompositeExtract %5 %40 3
%48 = OpCompositeExtract %5 %40 4
%49 = OpCompositeExtract %5 %40 5
%50 = OpCompositeExtract %5 %40 6
%51 = OpCompositeExtract %5 %40 7
%52 = OpCompositeExtract %5 %40 8
%53 = OpCompositeExtract %5 %40 9
%54 = OpCompositeExtract %5 %40 10
%55 = OpCompositeExtract %5 %40 11
%56 = OpCompositeExtract %5 %40 12
%57 = OpCompositeExtract %5 %40 13
%58 = OpCompositeExtract %5 %40 14
%59 = OpCompositeExtract %5 %40 15
%60 = OpCompositeConstruct %6 %44 %45 %46 %47 %48 %49 %50 %51 %52 %53 %54 %55 %56 %57 %58 %59
%61 = OpAccessChain %37 %14 %21 %43
OpBeginInvocationInterlockEXT
OpStore %61 %60 MakePointerAvailable|NonPrivatePointer %62
OpEndInvocationInterlockEXT
OpReturn
OpFunctionEnd
%29 = OpFunction %5 None %26
%27 = OpFunctionParameter %5
%28 = OpFunctionParameter %5
%30 = OpLabel
%31 = OpUDiv %5 %32 %28
%33 = OpBitwiseAnd %5 %27 %31
OpReturnValue %33
OpFunctionEnd

