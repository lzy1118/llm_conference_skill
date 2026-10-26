package org.grobid.core.utilities;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.apache.commons.io.IOUtils;
import org.junit.Test;

public class DataSetContextExtractorTest {

    @Test
    public void testRefEscapes() throws Exception {
        InputStream is = this.getClass().getResourceAsStream("/test/tei-escape.xml");
        String tei = IOUtils.toString(is, StandardCharsets.UTF_8);
        is.close();
        DataSetContextExtractor.getCitationReferences(tei);
    }

}
