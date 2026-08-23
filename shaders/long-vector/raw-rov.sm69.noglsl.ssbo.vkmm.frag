ByteAddressBuffer Input : register(t0);
RasterizerOrderedByteAddressBuffer Output : register(u0);

void main(float4 position : SV_Position)
{
	uint offset = uint(position.x) * 64;
	vector<uint, 16> value = Input.Load<vector<uint, 16> >(offset);
	Output.Store(offset, value + 1);
}
